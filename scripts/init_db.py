"""Initialize tables and demo assets in an already-created empty database."""

import logging
from pathlib import Path

from money_market_alert.config import initialize
from money_market_alert.storage.postgres import get_connection


def main() -> None:
    initialize()
    schema_path = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    with get_connection() as connection:
        # The schema file owns its BEGIN/COMMIT transaction (also usable via psql).
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(schema)
    logging.getLogger(__name__).info("Схема и пять компаний созданы")


if __name__ == "__main__":
    main()
