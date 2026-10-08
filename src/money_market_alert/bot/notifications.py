"""Delivery worker. The interactive bot runs as a separate process."""

import asyncio
import logging

from money_market_alert.config import get_float, get_int, initialize, require_env
from money_market_alert.storage.postgres import claim_alert, get_alert_candidates, save_alert_result
from money_market_alert.bot.messages import build_telegram_alert_message

logger = logging.getLogger(__name__)


async def send_ready_alerts(limit: int = 10) -> dict:
    from telegram import Bot
    from telegram.error import BadRequest, NetworkError, TelegramError

    token = require_env("BOT_TOKEN")
    candidates = get_alert_candidates(limit=limit)
    counts = {"sent": 0, "failed": 0, "pending": 0, "skipped": 0}
    if not candidates:
        logger.info("Нет готовых уведомлений")
        return counts
    delay = get_float("TELEGRAM_SEND_DELAY_SECONDS", 1)
    async with Bot(token=token) as bot:
        for index, alert in enumerate(candidates):
            if index:
                await asyncio.sleep(delay)
            message = build_telegram_alert_message(alert)
            values = {
                "user_id": alert["user_id"],
                "news_id": alert["news_id"],
                "analysis_id": alert["analysis_id"],
                "telegram_message": message,
            }
            if not claim_alert(**values):
                counts["skipped"] += 1
                continue
            try:
                await bot.send_message(chat_id=alert["telegram_id"], text=message)
            except TelegramError as error:
                if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
                    # The response can be lost after Telegram accepted the message.
                    # BadRequest also inherits NetworkError, but confirms rejection.
                    logger.warning(
                        "Доставка news_id=%s осталась pending: %s",
                        alert["news_id"], type(error).__name__,
                    )
                    counts["pending"] += 1
                    continue
                save_alert_result(**values, delivery_status="failed")
                logger.warning(
                    "Доставка news_id=%s не выполнена: %s",
                    alert["news_id"], type(error).__name__,
                )
                counts["failed"] += 1
                continue
            # A database error here must not turn an accepted message into failed.
            # The reserved pending row remains for operator inspection.
            save_alert_result(**values, delivery_status="sent")
            counts["sent"] += 1
    logger.info("Итог доставки: %s", counts)
    return counts


if __name__ == "__main__":
    initialize()
    asyncio.run(send_ready_alerts(limit=get_int("MAX_ALERTS_TO_SEND", 10)))
