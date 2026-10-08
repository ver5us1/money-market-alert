"""Offline preview: synthetic input, predefined analysis, real formatter."""

import json
from pathlib import Path

from money_market_alert.analysis.validation import validate_analysis
from money_market_alert.bot.messages import build_telegram_alert_message


def main() -> None:
    path = Path(__file__).with_name("demo-news.json")
    example = json.loads(path.read_text(encoding="utf-8"))
    analysis = validate_analysis(example["analysis"])
    print("ДЕМО: вымышленная новость, анализ задан заранее; отправка не выполняется.\n")
    print(build_telegram_alert_message({**example["news"], **analysis}))


if __name__ == "__main__":
    main()
