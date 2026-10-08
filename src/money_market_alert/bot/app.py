import logging

from money_market_alert.config import initialize, require_env

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from money_market_alert.storage.postgres import (
    upsert_user,
    get_assets,
    get_user_active_asset_ids,
    toggle_subscription,
    deactivate_all_subscriptions,
)


MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [["📋 Меню"]],
    resize_keyboard=True
)


def build_assets_keyboard(telegram_id: int):
    assets = get_assets()
    selected_asset_ids = get_user_active_asset_ids(telegram_id)

    keyboard = []

    for asset in assets:
        asset_id = asset["id"]
        ticker = asset["ticker"]
        company_name = asset["company_name"]

        if asset_id in selected_asset_ids:
            button_text = f"✅ {company_name} / {ticker}"
        else:
            button_text = f"☐ {company_name} / {ticker}"

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"toggle_asset:{asset_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="✅ Готово",
            callback_data="subscriptions_done"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def build_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(
                text="📌 Список подписок",
                callback_data="edit_subscriptions"
            )
        ],
        [
            InlineKeyboardButton(
                text="⛔ Остановить рассылку",
                callback_data="stop_subscriptions"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    telegram_id = telegram_user.id
    username = telegram_user.username

    upsert_user(telegram_id, username)

    welcome_text = (
        "Привет! Я MONEY Market Alert Bot.\n\n"
        "Я отслеживаю важные новости по выбранным компаниям "
        "и присылаю краткий AI-анализ.\n\n"
        "Для управления подписками нажмите кнопку 📋 Меню внизу."
    )

    await update.message.reply_text(
        text=welcome_text,
        reply_markup=MAIN_MENU_KEYBOARD
    )


async def handle_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    telegram_id = telegram_user.id
    username = telegram_user.username

    upsert_user(telegram_id, username)

    if update.message.text == "📋 Меню":
        await update.message.reply_text(
            text=(
                "📋 Меню MONEY Market Alert\n\n"
                "Выберите действие:"
            ),
            reply_markup=build_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text="Нажмите кнопку 📋 Меню, чтобы управлять подписками.",
            reply_markup=MAIN_MENU_KEYBOARD
        )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_user = query.from_user
    telegram_id = telegram_user.id
    username = telegram_user.username
    data = query.data

    upsert_user(telegram_id, username)

    if data == "edit_subscriptions":
        await query.edit_message_text(
            text=(
                "Изменение подписки.\n\n"
                "Нажмите на компанию, чтобы включить или отключить её из рассылки:"
            ),
            reply_markup=build_assets_keyboard(telegram_id)
        )

    elif data.startswith("toggle_asset:"):
        asset_id = int(data.split(":")[1])

        toggle_subscription(telegram_id, asset_id)

        await query.edit_message_text(
            text=(
                "Изменение подписки.\n\n"
                "Нажмите на компанию, чтобы включить или отключить её из рассылки:"
            ),
            reply_markup=build_assets_keyboard(telegram_id)
        )

    elif data == "subscriptions_done":
        selected_asset_ids = get_user_active_asset_ids(telegram_id)
        assets = get_assets()

        selected_assets = [
            asset for asset in assets
            if asset["id"] in selected_asset_ids
        ]

        if not selected_assets:
            text = (
                "Список подписок пуст.\n\n"
                "Рассылка сейчас не активна.\n\n"
                "Чтобы снова выбрать компании, откройте:\n"
                "📋 Меню → 📌 Список подписок."
            )
        else:
            text = (
                "Готово. Ваш список подписок сохранён.\n\n"
                "Сейчас вы отслеживаете:\n"
                + "\n".join(
                    f"• {asset['company_name']} / {asset['ticker']}"
                    for asset in selected_assets
                )
                + "\n\n"
                "Когда появится важная новость, бот пришлёт уведомление.\n\n"
                "Важно: уведомления носят информационно-аналитический характер "
                "и не являются индивидуальной инвестиционной рекомендацией."
            )

        await query.edit_message_text(
            text=text,
            reply_markup=build_menu_keyboard()
        )

    elif data == "stop_subscriptions":
        deactivated = deactivate_all_subscriptions(telegram_id)

        if deactivated:
            text = (
                "Рассылка остановлена.\n\n"
                "Все активные подписки отключены. "
                "Вы больше не будете получать уведомления по выбранным компаниям.\n\n"
                "Чтобы снова включить рассылку, откройте:\n"
                "📋 Меню → 📌 Список подписок."
            )
        else:
            text = (
                "У вас уже нет активных подписок.\n\n"
                "Чтобы выбрать компании, откройте:\n"
                "📋 Меню → 📌 Список подписок."
            )

        await query.edit_message_text(
            text=text,
            reply_markup=build_menu_keyboard()
        )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.getLogger(__name__).error(
        "Ошибка обработчика Telegram: %s", type(context.error).__name__
    )


def main():
    initialize()
    token = require_env("BOT_TOKEN")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_message))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_error_handler(handle_error)

    logging.getLogger(__name__).info("Бот запущен; доступна команда /start")
    app.run_polling()


if __name__ == "__main__":
    main()
