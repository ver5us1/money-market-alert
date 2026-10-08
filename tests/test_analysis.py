import copy
import json
import unittest
from pathlib import Path

from money_market_alert.analysis.validation import has_company_reference, validate_analysis
from money_market_alert.bot.messages import build_telegram_alert_message, clip_text

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples" / "demo-news.json").read_text(encoding="utf-8")
)


class AnalysisValidationTests(unittest.TestCase):
    def test_valid_result_is_trimmed_without_mutating_input(self):
        value = copy.deepcopy(EXAMPLE["analysis"])
        value["reasoning"] = "  Обоснование  "
        self.assertEqual(validate_analysis(value)["reasoning"], "Обоснование")
        self.assertEqual(value["reasoning"], "  Обоснование  ")

    def test_string_false_and_numeric_flags_are_rejected(self):
        for flag in ("false", "true", 0, 1, None):
            with self.subTest(flag=flag):
                value = {**EXAMPLE["analysis"], "is_relevant": flag}
                with self.assertRaises(ValueError):
                    validate_analysis(value)

    def test_unknown_classifications_are_rejected(self):
        for key, value in (("sentiment", "bullish"), ("importance", "urgent"), ("sentiment", [])):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_analysis({**EXAMPLE["analysis"], key: value})

    def test_irrelevant_news_is_neutral_and_low(self):
        result = validate_analysis({
            **EXAMPLE["analysis"], "is_relevant": False,
            "sentiment": "positive", "importance": "high",
        })
        self.assertEqual((result["sentiment"], result["importance"]), ("neutral", "low"))

    def test_missing_extra_and_non_object_output_are_rejected(self):
        missing = dict(EXAMPLE["analysis"])
        del missing["reasoning"]
        for value in (missing, {**EXAMPLE["analysis"], "extra": 1}, [], None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_analysis(value)

    def test_empty_non_string_or_oversize_text_is_rejected(self):
        for value in ("   ", None, 42, "я" * 4001):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                validate_analysis({**EXAMPLE["analysis"], "short_summary": value})


class RelevanceTests(unittest.TestCase):
    def news(self, text, ticker="AMD", company="Advanced Micro Devices"):
        return {"ticker": ticker, "company_name": company, "headline": text, "summary": ""}

    def test_ticker_is_a_whole_token(self):
        for text in ("$AMD earnings", "(amd): results", "AMD's report"):
            with self.subTest(text=text):
                self.assertTrue(has_company_reference(self.news(text)))

    def test_substring_and_generic_company_words_do_not_match(self):
        for text in ("ScamDetector releases an update", "Advanced cloud devices", "AMDX results"):
            with self.subTest(text=text):
                self.assertFalse(has_company_reference(self.news(text)))

    def test_company_alias_and_summary_are_matched(self):
        item = self.news("Quarterly results", "PLTR", "Palantir Technologies")
        item["summary"] = "Palantir released its report"
        self.assertTrue(has_company_reference(item))

    def test_empty_text_does_not_match(self):
        self.assertFalse(has_company_reference(self.news("")))


class MessageTests(unittest.TestCase):
    def test_demo_contains_summary_and_link(self):
        text = build_telegram_alert_message({**EXAMPLE["news"], **EXAMPLE["analysis"]})
        self.assertIn(EXAMPLE["analysis"]["short_summary"], text)
        self.assertIn(EXAMPLE["news"]["url"], text)

    def test_long_emoji_message_fits_telegram_limit(self):
        alert = {**EXAMPLE["news"], **EXAMPLE["analysis"]}
        for key in ("company_name", "ticker", "headline", "source", "url", "short_summary", "possible_impact"):
            alert[key] = "😀" * 5000
        text = build_telegram_alert_message(alert)
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
        self.assertTrue(text.endswith("индивидуальной инвестиционной рекомендацией."))

    def test_optional_source_and_url(self):
        alert = {**EXAMPLE["news"], **EXAMPLE["analysis"], "source": None, "url": None}
        text = build_telegram_alert_message(alert)
        self.assertIn("Источник: не указан", text)
        self.assertNotIn("Ссылка:", text)

    def test_truncation_does_not_split_emoji(self):
        self.assertEqual(clip_text("😀😀😀", 5), "😀😀…")
