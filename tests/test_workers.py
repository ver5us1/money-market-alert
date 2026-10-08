import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from money_market_alert.bot import notifications as alert_service
from money_market_alert.storage import postgres as db
from money_market_alert.services import ollama as llm_service
from money_market_alert.services import finnhub as news_service
from money_market_alert import scheduler
from money_market_alert.config import get_float, get_int

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples" / "demo-news.json").read_text(encoding="utf-8")
)


class ModelBoundaryTests(unittest.TestCase):
    def fake_requests(self, data):
        response = Mock()
        response.json.return_value = data
        module = types.ModuleType("requests")
        module.post = Mock(return_value=response)
        return module

    def test_unrelated_news_skips_http(self):
        fake = self.fake_requests({})
        with patch.dict(sys.modules, {"requests": fake}):
            result = llm_service.analyze_news_with_ollama({
                **EXAMPLE["news"], "headline": "General market report", "summary": "",
            })
        self.assertFalse(result["is_relevant"])
        fake.post.assert_not_called()

    def test_schema_and_config_are_used_for_http_request(self):
        fake = self.fake_requests({"response": json.dumps(EXAMPLE["analysis"])})
        env = {"OLLAMA_URL": "http://localhost:12345/api/generate", "OLLAMA_MODEL": "test-model"}
        with patch.dict(sys.modules, {"requests": fake}), patch.dict(os.environ, env):
            result = llm_service.analyze_news_with_ollama(EXAMPLE["news"])
        self.assertEqual(result, EXAMPLE["analysis"])
        args, kwargs = fake.post.call_args
        self.assertEqual(args[0], env["OLLAMA_URL"])
        self.assertEqual(kwargs["json"]["model"], "test-model")
        self.assertEqual(kwargs["json"]["format"]["type"], "object")
        self.assertFalse(kwargs["json"]["stream"])

    def test_malformed_or_invalid_model_output_is_rejected(self):
        outputs = ({}, {"response": "not-json"}, {"response": json.dumps({**EXAMPLE["analysis"], "is_relevant": "false"})})
        for output in outputs:
            with self.subTest(output=output):
                with patch.dict(sys.modules, {"requests": self.fake_requests(output)}):
                    with self.assertRaises(ValueError):
                        llm_service.analyze_news_with_ollama(EXAMPLE["news"])

    def test_invalid_analysis_is_not_saved_and_batch_continues(self):
        items = [{**EXAMPLE["news"], "id": 1}, {**EXAMPLE["news"], "id": 2}]
        with patch.object(llm_service, "get_new_news_items", return_value=items), \
             patch.object(llm_service, "analyze_news_with_ollama", side_effect=[ValueError("bad"), EXAMPLE["analysis"]]), \
             patch.object(llm_service, "save_news_analysis") as save:
            counts = llm_service.process_new_news()
        self.assertEqual(counts, {"processed": 1, "errors": 1})
        save.assert_called_once_with(2, EXAMPLE["analysis"])

    def test_db_rejects_invalid_analysis_before_opening_connection(self):
        with patch.object(db, "get_connection") as connect:
            with self.assertRaises(ValueError):
                db.save_news_analysis(1, {**EXAMPLE["analysis"], "is_relevant": "false"})
        connect.assert_not_called()


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def run_delivery(self, send_error=None, claimed=True, save_error=None):
        telegram = types.ModuleType("telegram")
        errors = types.ModuleType("telegram.error")
        class TelegramError(Exception):
            pass
        class NetworkError(TelegramError):
            pass
        class BadRequest(NetworkError):
            pass
        errors.TelegramError = TelegramError
        errors.NetworkError = NetworkError
        errors.BadRequest = BadRequest
        bot = Mock()
        if send_error == "network":
            exception = NetworkError("ambiguous response")
        elif send_error == "api":
            exception = TelegramError("request rejected")
        elif send_error == "bad-request":
            exception = BadRequest("invalid request")
        else:
            exception = None
        bot.send_message = AsyncMock(side_effect=exception)
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=bot)
        context.__aexit__ = AsyncMock(return_value=False)
        telegram.Bot = Mock(return_value=context)
        alert = {**EXAMPLE["news"], **EXAMPLE["analysis"], "user_id": 1, "news_id": 2, "analysis_id": 3, "telegram_id": 4}
        with patch.dict(sys.modules, {"telegram": telegram, "telegram.error": errors}), \
             patch.dict(os.environ, {"BOT_TOKEN": "test-placeholder", "TELEGRAM_SEND_DELAY_SECONDS": "0"}), \
             patch.object(alert_service, "get_alert_candidates", return_value=[alert]), \
             patch.object(alert_service, "claim_alert", return_value={"id": 1} if claimed else None) as claim, \
             patch.object(alert_service, "save_alert_result", side_effect=save_error) as save:
            counts = await alert_service.send_ready_alerts()
        return counts, bot, claim, save, context

    async def test_success_updates_sent_and_closes_client(self):
        counts, bot, claim, save, context = await self.run_delivery()
        self.assertEqual(counts["sent"], 1)
        claim.assert_called_once()
        bot.send_message.assert_awaited_once()
        self.assertEqual(save.call_args.kwargs["delivery_status"], "sent")
        context.__aexit__.assert_awaited_once()

    async def test_already_reserved_delivery_is_not_sent(self):
        counts, bot, _, save, _ = await self.run_delivery(claimed=False)
        self.assertEqual(counts["skipped"], 1)
        bot.send_message.assert_not_awaited()
        save.assert_not_called()

    async def test_definitive_api_failure_is_retryable(self):
        counts, _, _, save, _ = await self.run_delivery(send_error="api")
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(save.call_args.kwargs["delivery_status"], "failed")

    async def test_uncertain_network_delivery_remains_pending(self):
        counts, _, _, save, _ = await self.run_delivery(send_error="network")
        self.assertEqual(counts["pending"], 1)
        save.assert_not_called()

    async def test_bad_request_is_rejected_even_though_it_is_network_error_subclass(self):
        counts, _, _, save, _ = await self.run_delivery(send_error="bad-request")
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(save.call_args.kwargs["delivery_status"], "failed")

    async def test_db_failure_after_send_is_not_marked_failed(self):
        with self.assertRaises(RuntimeError):
            await self.run_delivery(save_error=RuntimeError("database unavailable"))


class FetchAndScheduleTests(unittest.TestCase):
    def test_finnhub_error_object_is_not_treated_as_news(self):
        response = Mock()
        response.json.return_value = {"error": "API limit"}
        fake = types.ModuleType("requests")
        fake.get = Mock(return_value=response)
        with patch.dict(sys.modules, {"requests": fake}), patch.dict(os.environ, {"FINNHUB_API_KEY": "placeholder"}):
            with self.assertRaises(ValueError):
                news_service.fetch_company_news("NVDA")

    def test_schedule_accounts_for_work_duration_without_overlap(self):
        self.assertEqual(scheduler.seconds_until_next_run(900, 120), 780)
        self.assertEqual(scheduler.seconds_until_next_run(900, 1000), 1)

    def test_invalid_intervals_and_nonfinite_delays_are_rejected(self):
        for value in ("0", "-1", "oops"):
            with patch.dict(os.environ, {"TEST_INTERVAL": value}), self.assertRaises(ValueError):
                get_int("TEST_INTERVAL", 900)
        for value in ("nan", "inf", "-2"):
            with patch.dict(os.environ, {"TEST_DELAY": value}), self.assertRaises(ValueError):
                get_float("TEST_DELAY", 1)


if __name__ == "__main__":
    unittest.main()
