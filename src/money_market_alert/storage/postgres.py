from money_market_alert.analysis.validation import validate_analysis
from money_market_alert.config import require_env


def get_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        require_env("DATABASE_URL"), row_factory=dict_row, connect_timeout=10
    )


def upsert_user(telegram_id: int, username: str | None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (telegram_id, username)
                VALUES (%s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET username = EXCLUDED.username
                RETURNING id, telegram_id, username, created_at;
                """,
                (telegram_id, username)
            )

            return cur.fetchone()


def get_assets():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ticker, company_name
                FROM assets
                WHERE is_active = TRUE
                ORDER BY ticker;
                """
            )

            return cur.fetchall()


def get_user_active_asset_ids(telegram_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.asset_id
                FROM user_subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE u.telegram_id = %s
                  AND s.is_active = TRUE;
                """,
                (telegram_id,)
            )

            rows = cur.fetchall()
            return {row["asset_id"] for row in rows}


def toggle_subscription(telegram_id: int, asset_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM users
                WHERE telegram_id = %s;
                """,
                (telegram_id,)
            )

            user = cur.fetchone()

            if not user:
                raise ValueError("Пользователь не найден в базе")

            user_id = user["id"]

            cur.execute(
                """
                SELECT id, is_active
                FROM user_subscriptions
                WHERE user_id = %s
                  AND asset_id = %s;
                """,
                (user_id, asset_id)
            )

            subscription = cur.fetchone()

            if subscription is None:
                cur.execute(
                    """
                    INSERT INTO user_subscriptions (user_id, asset_id, is_active)
                    VALUES (%s, %s, TRUE)
                    RETURNING id, user_id, asset_id, is_active;
                    """,
                    (user_id, asset_id)
                )

                return cur.fetchone()

            new_status = not subscription["is_active"]

            cur.execute(
                """
                UPDATE user_subscriptions
                SET is_active = %s
                WHERE id = %s
                RETURNING id, user_id, asset_id, is_active;
                """,
                (new_status, subscription["id"])
            )

            return cur.fetchone()


def deactivate_all_subscriptions(telegram_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_subscriptions s
                SET is_active = FALSE
                FROM users u
                WHERE s.user_id = u.id
                  AND u.telegram_id = %s
                  AND s.is_active = TRUE
                RETURNING s.id, s.asset_id, s.is_active;
                """,
                (telegram_id,)
            )

            return cur.fetchall()


def save_news_item(symbol: str, item: dict):
    external_id = item.get("id")

    if not external_id:
        return None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM assets
                WHERE ticker = %s;
                """,
                (symbol,)
            )

            asset = cur.fetchone()

            if not asset:
                raise ValueError(f"Актив {symbol} не найден в базе")

            asset_id = asset["id"]

            cur.execute(
                """
                INSERT INTO news_items (
                    external_id,
                    asset_id,
                    source,
                    headline,
                    summary,
                    url,
                    published_at,
                    processing_status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    TO_TIMESTAMP(%s),
                    'new'
                )
                ON CONFLICT (external_id) DO NOTHING
                RETURNING id, external_id, asset_id, headline, processing_status;
                """,
                (
                    external_id,
                    asset_id,
                    item.get("source"),
                    item.get("headline") or "Без заголовка",
                    item.get("summary"),
                    item.get("url"),
                    item.get("datetime"),
                )
            )

            return cur.fetchone()

def get_new_news_items(limit: int = 5):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    n.id,
                    a.ticker,
                    a.company_name,
                    n.external_id,
                    n.source,
                    n.headline,
                    n.summary,
                    n.url,
                    n.published_at,
                    n.processing_status
                FROM news_items n
                JOIN assets a ON n.asset_id = a.id
                WHERE n.processing_status = 'new'
                  AND a.is_active = TRUE
                ORDER BY n.published_at ASC, n.id ASC
                LIMIT %s;
                """,
                (limit,)
            )

            return cur.fetchall()


def save_news_analysis(news_id: int, analysis: dict):
    analysis = validate_analysis(analysis)
    is_relevant = analysis["is_relevant"]
    sentiment = analysis["sentiment"]
    importance = analysis["importance"]
    short_summary = analysis["short_summary"]
    reasoning = analysis["reasoning"]
    possible_impact = analysis["possible_impact"]

    if is_relevant:
        processing_status = "analyzed"
    else:
        processing_status = "rejected"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_analysis (
                    news_id,
                    is_relevant,
                    sentiment,
                    importance,
                    short_summary,
                    reasoning,
                    possible_impact
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (news_id)
                DO UPDATE SET
                    is_relevant = EXCLUDED.is_relevant,
                    sentiment = EXCLUDED.sentiment,
                    importance = EXCLUDED.importance,
                    short_summary = EXCLUDED.short_summary,
                    reasoning = EXCLUDED.reasoning,
                    possible_impact = EXCLUDED.possible_impact
                RETURNING id, news_id, is_relevant, sentiment, importance;
                """,
                (
                    news_id,
                    is_relevant,
                    sentiment,
                    importance,
                    short_summary,
                    reasoning,
                    possible_impact
                )
            )

            saved_analysis = cur.fetchone()

            cur.execute(
                """
                UPDATE news_items
                SET processing_status = %s
                WHERE id = %s
                RETURNING id, processing_status;
                """,
                (processing_status, news_id)
            )

            updated_news = cur.fetchone()

            return {
                "analysis": saved_analysis,
                "news": updated_news
            }

def get_alert_candidates(limit: int = 10):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.telegram_id,
                    u.username,

                    a.id AS asset_id,
                    a.ticker,
                    a.company_name,

                    n.id AS news_id,
                    n.headline,
                    n.source,
                    n.url,
                    n.published_at,

                    na.id AS analysis_id,
                    na.sentiment,
                    na.importance,
                    na.short_summary,
                    na.possible_impact
                FROM news_analysis na
                JOIN news_items n ON na.news_id = n.id
                JOIN assets a ON n.asset_id = a.id
                JOIN user_subscriptions s ON s.asset_id = a.id
                JOIN users u ON s.user_id = u.id
                LEFT JOIN alerts al
                    ON al.user_id = u.id
                   AND al.news_id = n.id
                WHERE na.is_relevant = TRUE
                  AND na.importance IN ('medium', 'high')
                  AND a.is_active = TRUE
                  AND s.is_active = TRUE
                  AND (al.id IS NULL OR al.delivery_status = 'failed')
                ORDER BY n.published_at DESC
                LIMIT %s;
                """,
                (limit,)
            )

            return cur.fetchall()


def claim_alert(
    user_id: int,
    news_id: int,
    analysis_id: int,
    telegram_message: str,
):
    """Reserve a new or explicitly failed delivery before contacting Telegram."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (
                    user_id, news_id, analysis_id, telegram_message, delivery_status
                )
                VALUES (%s, %s, %s, %s, 'pending')
                ON CONFLICT (user_id, news_id)
                DO UPDATE SET
                    analysis_id = EXCLUDED.analysis_id,
                    telegram_message = EXCLUDED.telegram_message,
                    sent_at = NULL,
                    delivery_status = 'pending'
                WHERE alerts.delivery_status = 'failed'
                RETURNING id, user_id, news_id, delivery_status;
                """,
                (user_id, news_id, analysis_id, telegram_message),
            )
            return cur.fetchone()


def save_alert_result(
    user_id: int,
    news_id: int,
    analysis_id: int,
    telegram_message: str,
    delivery_status: str
):
    if delivery_status not in {"sent", "failed"}:
        raise ValueError("Результат доставки должен быть sent или failed")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (
                    user_id,
                    news_id,
                    analysis_id,
                    telegram_message,
                    sent_at,
                    delivery_status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    CASE
                        WHEN %s = 'sent' THEN NOW()
                        ELSE NULL
                    END,
                    %s
                )
                ON CONFLICT (user_id, news_id)
                DO UPDATE SET
                    analysis_id = EXCLUDED.analysis_id,
                    telegram_message = EXCLUDED.telegram_message,
                    sent_at = EXCLUDED.sent_at,
                    delivery_status = EXCLUDED.delivery_status
                WHERE alerts.delivery_status <> 'sent'
                RETURNING id, user_id, news_id, analysis_id, delivery_status, sent_at;
                """,
                (
                    user_id,
                    news_id,
                    analysis_id,
                    telegram_message,
                    delivery_status,
                    delivery_status
                )
            )

            return cur.fetchone()
