# Модель данных

| Таблица | Назначение | Уникальность |
| --- | --- | --- |
| `users` | Пользователи Telegram | `telegram_id` |
| `assets` | Компании и тикеры | `ticker` |
| `user_subscriptions` | Подписки пользователя на компанию | `user_id`, `asset_id` |
| `news_items` | Новости из Finnhub | `external_id` |
| `news_analysis` | Структурированный анализ новости | `news_id` |
| `alerts` | Текст и состояние отправки | `user_id`, `news_id` |

```mermaid
erDiagram
    USERS ||--o{ USER_SUBSCRIPTIONS : selects
    ASSETS ||--o{ USER_SUBSCRIPTIONS : tracks
    ASSETS ||--o{ NEWS_ITEMS : receives
    NEWS_ITEMS ||--o| NEWS_ANALYSIS : analyzed
    USERS ||--o{ ALERTS : receives
    NEWS_ITEMS ||--o{ ALERTS : produces
    NEWS_ANALYSIS ||--o{ ALERTS : explains
```

Начальная схема: [schema.sql](schema.sql). Исходное описание: [data-model.docx](../docs/models/data-model.docx); изображение из него: [data-model.png](../docs/models/data-model.png).

Таблицы связаны внешними ключами. Временные поля используют `TIMESTAMPTZ`; очереди новостей и подписки имеют индексы. В схему включены пять компаний MVP.

Одна новость сейчас связана с одним активом, а внешний ID уникален во всей новостной таблице. Поддержка нескольких компаний в одной новости потребует отдельной связи и миграции.

`schema.sql` описывает новый экземпляр БД. История миграций существующей базы пока не реализована; эта схема не заменяет миграцию данных.
