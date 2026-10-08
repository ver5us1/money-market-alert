"""Notification formatting, without a Telegram connection."""


def clip_text(value: object, budget: int) -> str:
    """Use UTF-16 units as a conservative limit, including emoji."""
    text = str(value or "").strip()
    if len(text.encode("utf-16-le")) // 2 <= budget:
        return text
    kept = []
    used = 0
    for char in text:
        units = len(char.encode("utf-16-le")) // 2
        if used + units > budget - 1:
            break
        kept.append(char)
        used += units
    return "".join(kept).rstrip() + "…"


def build_telegram_alert_message(alert: dict) -> str:
    sentiment = {
        "positive": "позитивная", "negative": "негативная", "neutral": "нейтральная",
    }.get(alert["sentiment"], "не определена")
    importance = {
        "low": "низкая", "medium": "средняя", "high": "высокая",
    }.get(alert["importance"], "не определена")
    message = (
        "🚨 MONEY Market Alert\n\n"
        f"Компания: {clip_text(alert['company_name'], 120)} / {clip_text(alert['ticker'], 20)}\n"
        f"Важность: {importance}\nТональность: {sentiment}\n\n"
        f"Кратко:\n{clip_text(alert['short_summary'], 900)}\n\n"
        f"Возможное влияние:\n{clip_text(alert['possible_impact'], 900)}\n\n"
        f"Источник: {clip_text(alert.get('source') or 'не указан', 120)}\n"
        f"Заголовок: {clip_text(alert['headline'], 500)}\n"
    )
    if alert.get("url"):
        message += f"\nСсылка: {clip_text(alert['url'], 500)}\n"
    return message + (
        "\nВажно: уведомление носит информационно-аналитический характер "
        "и не является индивидуальной инвестиционной рекомендацией."
    )
