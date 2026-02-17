import sqlite3
from datetime import datetime, time
import pytz
import tzlocal
import os
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

# ======================
# CONFIG
# ======================
TOKEN = os.getenv("TOKEN")

UTC = pytz.utc
TIME_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# ======================
# STATES
# ======================
TITLE, COUNTRY, CITY, DATE, TIME, RECURRENCE = range(6)
EDIT_TIME = 100

# ======================
# DATABASE
# ======================
def init_db():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            datetime_utc TEXT,
            country TEXT,
            city TEXT,
            recurrence TEXT
        )
    """)
    conn.commit()
    conn.close()

# ======================
# /NOVO
# ======================
async def novo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Dê um nome ao seu evento:")
    return TITLE

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("🌍 Informe o país:")
    return COUNTRY

async def set_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["country"] = update.message.text.strip()
    await update.message.reply_text("🏙 Informe a cidade:")
    return CITY

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    calendar, _ = DetailedTelegramCalendar().build()
    await update.message.reply_text("📅 Selecione a data:", reply_markup=calendar)
    return DATE

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    result, key, step = DetailedTelegramCalendar().process(query.data)

    if not result and key:
        await query.edit_message_text(
            f"📅 Selecione {LSTEP[step]}:",
            reply_markup=key
        )
        return DATE

    context.user_data["date"] = result
    await query.edit_message_text("⏰ Informe o horário (HH:MM):")
    return TIME

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not TIME_REGEX.match(text):
        await update.message.reply_text("❌ Formato inválido. Use HH:MM (ex: 09:30)")
        return TIME

    hour, minute = map(int, text.split(":"))

    local_tz = tzlocal.get_localzone()
    date = context.user_data["date"]

    local_dt = local_tz.localize(
        datetime.combine(date, time(hour, minute))
    )

    utc_dt = local_dt.astimezone(UTC)
    context.user_data["datetime_utc"] = utc_dt.isoformat()

    keyboard = [
        [InlineKeyboardButton("🔁 Apenas uma vez", callback_data="none")],
        [InlineKeyboardButton("📅 Diário", callback_data="daily")],
        [InlineKeyboardButton("🗓 Mensal", callback_data="monthly")],
    ]

    await update.message.reply_text(
        "Escolha a recorrência:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return RECURRENCE

async def set_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    

    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reminders 
        (user_id, title, datetime_utc, country, city, recurrence)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        query.from_user.id,
        context.user_data["title"],
        context.user_data["datetime_utc"],
        context.user_data["country"],
        context.user_data["city"],
        query.data
    ))
    conn.commit()
    conn.close()

    await query.edit_message_text("✅ Evento criado com sucesso!")
    return ConversationHandler.END

# ======================
# LISTA
# ======================
def build_event_menu(user_id):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM reminders WHERE user_id = ?", (user_id,))
    events = cursor.fetchall()
    conn.close()

    if not events:
        return None

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(title, callback_data=f"view_{eid}")]
        for eid, title in events
    ])

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = build_event_menu(update.effective_user.id)
    if not menu:
        await update.message.reply_text("Você não possui eventos.")
        return
    await update.message.reply_text("📋 Seus eventos:", reply_markup=menu)

async def view_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    event_id = query.data.split("_")[1]
    context.user_data["edit_id"] = event_id

    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, datetime_utc, country, city, recurrence
        FROM reminders WHERE id = ?
    """, (event_id,))
    event = cursor.fetchone()
    conn.close()

    if not event:
        await query.edit_message_text("❌ Evento não encontrado.")
        return

    title, dt_utc, country, city, recurrence = event
    local_dt = datetime.fromisoformat(dt_utc).astimezone(
        tzlocal.get_localzone()
    )

    message = (
        f"📝 {title}\n\n"
        f"📅 {local_dt.strftime('%d-%m-%Y')}\n"
        f"⏰ {local_dt.strftime('%H:%M')}\n"
        f"📍 {city}, {country}\n"
        f"🔁 {recurrence}"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Editar horário", callback_data="edit_time")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back")]
    ]

    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================
# EDIT TIME
# ======================
async def edit_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏰ Digite o novo horário (HH:MM):")
    return EDIT_TIME

async def save_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not TIME_REGEX.match(text):
        await update.message.reply_text("❌ Formato inválido. Use HH:MM")
        return EDIT_TIME

    hour, minute = map(int, text.split(":"))
    event_id = context.user_data["edit_id"]

    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT datetime_utc FROM reminders WHERE id = ?", (event_id,))
    old_dt = datetime.fromisoformat(cursor.fetchone()[0])

    new_dt = old_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

    cursor.execute(
        "UPDATE reminders SET datetime_utc = ? WHERE id = ?",
        (new_dt.isoformat(), event_id)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Horário atualizado!")
    return ConversationHandler.END

# ======================
# START
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Bot de Lembretes\n\n"
        "/novo – Criar evento\n"
        "/lista – Ver eventos"
    )

# ======================
# MAIN
# ======================
def main():
    init_db()
    

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("novo", novo)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_title)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_country)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city)],
            DATE: [CallbackQueryHandler(calendar_handler)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time)],
            RECURRENCE: [CallbackQueryHandler(set_recurrence)],
        },
        fallbacks=[CommandHandler("start", start)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_time, pattern="^edit_time$")],
        states={
            EDIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_time)],
        },
        fallbacks=[CommandHandler("start", start)],
    ))

    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CallbackQueryHandler(view_event, pattern="^view_"))

    app.run_polling()

if __name__ == "__main__":
    main()
