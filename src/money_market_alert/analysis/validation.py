"""Pure relevance filtering and validation of model output."""

import re


COMPANY_ALIASES = {
    "TSLA": ("Tesla",),
    "NVDA": ("NVIDIA",),
    "AMD": ("Advanced Micro Devices",),
    "PLTR": ("Palantir",),
    "META": ("Meta", "Meta Platforms"),
}
SENTIMENTS = {"positive", "negative", "neutral"}
IMPORTANCE_LEVELS = {"low", "medium", "high"}
TEXT_FIELDS = ("short_summary", "reasoning", "possible_impact")
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "is_relevant": {"type": "boolean"},
        "sentiment": {"type": "string", "enum": sorted(SENTIMENTS)},
        "importance": {"type": "string", "enum": sorted(IMPORTANCE_LEVELS)},
        **{name: {"type": "string", "minLength": 1, "maxLength": 4000}
           for name in TEXT_FIELDS},
    },
    "required": ["is_relevant", "sentiment", "importance", *TEXT_FIELDS],
    "additionalProperties": False,
}


def has_company_reference(news_item: dict) -> bool:
    ticker = str(news_item["ticker"]).strip().upper()
    names = [ticker, str(news_item["company_name"]).strip()]
    names.extend(COMPANY_ALIASES.get(ticker, ()))
    text = f"{news_item.get('headline') or ''} {news_item.get('summary') or ''}"
    return any(
        name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I)
        for name in names
    )


def validate_analysis(analysis: object) -> dict:
    if not isinstance(analysis, dict):
        raise ValueError("Ответ LLM должен быть JSON-объектом")
    required = set(ANALYSIS_SCHEMA["required"])
    if set(analysis) != required:
        raise ValueError("Ответ LLM содержит пропущенные или лишние поля")
    if type(analysis["is_relevant"]) is not bool:
        raise ValueError("is_relevant должен быть boolean, а не строкой или числом")
    for name, allowed in (("sentiment", SENTIMENTS), ("importance", IMPORTANCE_LEVELS)):
        if not isinstance(analysis[name], str) or analysis[name] not in allowed:
            raise ValueError(f"Недопустимое значение {name}")
    result = dict(analysis)
    for name in TEXT_FIELDS:
        value = analysis[name]
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError(f"{name}: нужна непустая строка длиной до 4000 символов")
        result[name] = value.strip()
    if not result["is_relevant"]:
        result["sentiment"] = "neutral"
        result["importance"] = "low"
    return result
