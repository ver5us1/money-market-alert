"""Finnhub Company News adapter."""

import logging
from datetime import datetime, timedelta, timezone

from money_market_alert.config import get_int, initialize, require_env

FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"


def fetch_company_news(symbol: str, days_back: int = 2) -> list[dict]:
    import requests

    today = datetime.now(timezone.utc).date()
    params = {
        "symbol": symbol,
        "from": (today - timedelta(days=days_back)).isoformat(),
        "to": today.isoformat(),
        "token": require_env("FINNHUB_API_KEY"),
    }
    response = requests.get(FINNHUB_COMPANY_NEWS_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("Finnhub вернул ответ, отличный от списка новостей")
    return data


if __name__ == "__main__":
    initialize()
    news = fetch_company_news("NVDA", days_back=get_int("NEWS_DAYS_BACK", 2))
    logging.getLogger(__name__).info("Получено новостей NVDA: %s", len(news))
