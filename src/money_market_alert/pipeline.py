"""One collection → analysis → delivery cycle."""

import asyncio
import logging
import time

from money_market_alert.bot.notifications import send_ready_alerts
from money_market_alert.config import get_float, get_int, initialize
from money_market_alert.storage.postgres import get_assets, save_news_item
from money_market_alert.services.ollama import process_new_news
from money_market_alert.services.finnhub import fetch_company_news

logger = logging.getLogger(__name__)


def collect_news_for_all_assets() -> dict:
    assets = get_assets()
    days_back = get_int("NEWS_DAYS_BACK", 2)
    delay = get_float("NEWS_REQUEST_DELAY_SECONDS", 2)
    counts = {"received": 0, "saved": 0, "duplicates_or_skipped": 0, "errors": 0}
    for index, asset in enumerate(assets):
        symbol = asset["ticker"]
        try:
            news_items = fetch_company_news(symbol=symbol, days_back=days_back)
            counts["received"] += len(news_items)
            for item in news_items:
                if save_news_item(symbol, item):
                    counts["saved"] += 1
                else:
                    counts["duplicates_or_skipped"] += 1
        except Exception as error:
            # Exception URLs can contain a Finnhub API key. Do not log their text.
            logger.error("Получение новостей %s: %s", symbol, type(error).__name__)
            counts["errors"] += 1
        if index < len(assets) - 1:
            time.sleep(delay)
    logger.info("Итог сбора: %s", counts)
    return counts


async def run_pipeline() -> None:
    logger.info("Запуск цикла MONEY Market Alert")
    collect_news_for_all_assets()
    process_new_news(limit=get_int("MAX_NEWS_TO_ANALYZE", 5))
    await send_ready_alerts(limit=get_int("MAX_ALERTS_TO_SEND", 10))
    logger.info("Цикл завершён")


if __name__ == "__main__":
    initialize()
    asyncio.run(run_pipeline())
