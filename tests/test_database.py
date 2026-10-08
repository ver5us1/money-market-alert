"""Real SQL roundtrip, opt-in only on a disposable database ending in _ci."""

import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from money_market_alert.storage import postgres as db


@unittest.skipUnless(os.getenv("RUN_DATABASE_TESTS") == "1", "Нужна отдельная тестовая PostgreSQL БД")
class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv("DATABASE_URL", "")
        if not urlsplit(url).path.endswith("_ci"):
            raise RuntimeError("Интеграционный тест разрешён только для БД с суффиксом _ci")

    def test_subscription_news_analysis_and_delivery_roundtrip(self):
        sequence = time.time_ns()
        user = db.upsert_user(sequence, "ci_synthetic_user")
        self.assertEqual(db.upsert_user(sequence, "ci_updated")["id"], user["id"])
        assets = db.get_assets()
        self.assertEqual({a["ticker"] for a in assets}, {"TSLA", "NVDA", "AMD", "PLTR", "META"})
        asset = next(a for a in assets if a["ticker"] == "NVDA")
        db.toggle_subscription(sequence, asset["id"])
        self.assertIn(asset["id"], db.get_user_active_asset_ids(sequence))
        item = {
            "id": sequence, "datetime": 1700000000, "source": "CI fixture",
            "headline": "NVIDIA synthetic test event", "summary": "Synthetic data",
            "url": "https://example.org/ci",
        }
        news = db.save_news_item("NVDA", item)
        self.assertIsNotNone(news)
        self.assertIsNone(db.save_news_item("NVDA", item))
        self.assertIn(news["id"], {n["id"] for n in db.get_new_news_items(1000)})
        analysis = {
            "is_relevant": True, "sentiment": "neutral", "importance": "low",
            "short_summary": "Тест", "reasoning": "Тест", "possible_impact": "Тест",
        }
        db.save_news_analysis(news["id"], analysis)
        self.assertNotIn(news["id"], {a["news_id"] for a in db.get_alert_candidates(1000)})
        result = db.save_news_analysis(news["id"], {**analysis, "importance": "high"})
        candidates = db.get_alert_candidates(1000)
        self.assertIn((user["id"], news["id"]), {(a["user_id"], a["news_id"]) for a in candidates})
        values = {
            "user_id": user["id"], "news_id": news["id"],
            "analysis_id": result["analysis"]["id"], "telegram_message": "CI: no Telegram send",
        }
        self.assertIsNotNone(db.claim_alert(**values))
        self.assertIsNone(db.claim_alert(**values))
        db.save_alert_result(**values, delivery_status="failed")
        self.assertIn(news["id"], {a["news_id"] for a in db.get_alert_candidates(1000)})
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: db.claim_alert(**values), range(2)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        sent = db.save_alert_result(**values, delivery_status="sent")
        self.assertIsNotNone(sent["sent_at"])
        self.assertIsNone(db.claim_alert(**values))
        self.assertIsNone(db.save_alert_result(**values, delivery_status="failed"))
        self.assertNotIn(news["id"], {a["news_id"] for a in db.get_alert_candidates(1000)})
        db.deactivate_all_subscriptions(sequence)
        self.assertNotIn(asset["id"], db.get_user_active_asset_ids(sequence))


if __name__ == "__main__":
    unittest.main()
