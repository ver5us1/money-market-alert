"""Sequential scheduling: one event loop, no overlapping pipeline runs."""

import asyncio
import logging
import time

from money_market_alert.config import get_int, initialize
from money_market_alert.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def seconds_until_next_run(interval: int, elapsed: float) -> float:
    return max(1.0, interval - elapsed)


async def run_scheduler() -> None:
    interval = get_int("RUN_INTERVAL_SECONDS", 900)
    logger.info("Обработчик запущен; интервал между началами циклов %s с", interval)
    while True:
        started = time.monotonic()
        try:
            await run_pipeline()
        except Exception as error:
            logger.error("Ошибка цикла: %s", type(error).__name__)
        delay = seconds_until_next_run(interval, time.monotonic() - started)
        logger.info("Следующий цикл через %.1f с", delay)
        await asyncio.sleep(delay)


def main() -> None:
    initialize()
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        logger.info("Обработчик остановлен")


if __name__ == "__main__":
    main()
