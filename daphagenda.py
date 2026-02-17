import sqlite3
from datetime import datetime
import pytz
import tzlocal


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

import os
TOKEN = os.getenv("TOKEN")


TITLE, COUNTRY, CITY, DATE, TIME, RECURRENCE, EDIT_TIME = range(7)

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
            datetime TEXT,
            country TEXT,
            city TEXT,
            recurrence TEXT
        )
    """)
    conn.commit()
    conn.close()

# ======================
# /NOVO FLOW
# ======================

async def novo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chat.send_message("📝 Dê um nome ao seu evento:")
    return TITLE

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text
    await update.message.reply_text("🌍 Informe o país do evento:")
    return COUNTRY

async def set_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["country"] = update.message.text
    await update.message.reply_text("🏙️ Informe a cidade do evento:")
    return CITY

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    calendar, step = DetailedTelegramCalendar().build()
    await update.message.reply_text(
        f"📅 Selecione a data:",
        reply_markup=calendar
    )
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
    elif result:
        context.user_data["date"] = result
        await query.edit_message_text(
            f"📅 Data selecionada: {result.strftime('%d-%m-%Y')}\n\n"
            f"⏰ Agora informe o horário (HH:MM):"
        )
        return TIME

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_input = update.message.text
        hour, minute = map(int, time_input.split(":"))

        date = context.user_data["date"]
        local_tz = tzlocal.get_localzone()

        dt = datetime(date.year, date.month, date.day, hour, minute)
        dt = local_tz.localize(dt)

        context.user_data["datetime"] = dt.isoformat()

        keyboard = [
            [
                InlineKeyboardButton("🔁 Apenas uma vez", callback_data="none"),
                InlineKeyboardButton("📅 Diário", callback_data="daily"),
                InlineKeyboardButton("🗓️ Mensal", callback_data="monthly"),
            ]
        ]

        await update.message.reply_text(
            "Escolha a recorrência:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return RECURRENCE

    except:
        await update.message.reply_text("Formato inválido. Use HH:MM")
        return TIME

async def set_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    recurrence = query.data

    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reminders (user_id, title, datetime, country, city, recurrence)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        query.from_user.id,
        context.user_data["title"],
        context.user_data["datetime"],
        context.user_data["country"],
        context.user_data["city"],
        recurrence
    ))
    conn.commit()
    conn.close()

    await query.edit_message_text("✅ Evento criado com sucesso!")
    return ConversationHandler.END

# ======================
# MENU BUILDER
# ======================

def build_event_menu(user_id):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM reminders WHERE user_id = ?", (user_id,))
    events = cursor.fetchall()
    conn.close()

    if not events:
        return None

    keyboard = [
        [InlineKeyboardButton(event[1], callback_data=f"view_{event[0]}")]
        for event in events
    ]

    return InlineKeyboardMarkup(keyboard)

# ======================
# /LISTA
# ======================

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
        SELECT title, datetime, country, city, recurrence
        FROM reminders WHERE id = ?
    """, (event_id,))
    event = cursor.fetchone()
    conn.close()

    title, dt_str, country, city, recurrence = event
    dt = datetime.fromisoformat(dt_str)

    date = dt.strftime("%d-%m-%Y")
    time = dt.strftime("%H:%M")

    recurrence_map = {
        "none": "Apenas uma vez",
        "daily": "Diário",
        "monthly": "Mensal"
    }

    message = (
        f"📝 Nome: {title}\n\n"
        f"📅 Data: {date}\n"
        f"⏰ Hora: {time}\n"
        f"📍 Local: {city}, {country}\n"
        f"🔁 Recorrência: {recurrence_map.get(recurrence)}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✏️ Editar horário", callback_data="edit_time")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="back_to_list")
        ]
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# EDIT TIME
# ======================

async def edit_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏰ Digite o novo horário (HH:MM):")
    return EDIT_TIME

async def save_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hour, minute = map(int, update.message.text.split(":"))

        event_id = context.user_data["edit_id"]

        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("SELECT datetime FROM reminders WHERE id = ?", (event_id,))
        old_dt = datetime.fromisoformat(cursor.fetchone()[0])

        new_dt = old_dt.replace(hour=hour, minute=minute)

        cursor.execute(
            "UPDATE reminders SET datetime = ? WHERE id = ?",
            (new_dt.isoformat(), event_id)
        )
        conn.commit()
        conn.close()

        await update.message.reply_text("✅ Horário atualizado!")
        return ConversationHandler.END

    except:
        await update.message.reply_text("Formato inválido. Use HH:MM")
        return EDIT_TIME

async def back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    menu = build_event_menu(query.from_user.id)

    if not menu:
        await query.edit_message_text("Você não possui eventos.")
        return

    await query.edit_message_text("📋 Seus eventos:", reply_markup=menu)
# ======================
# /START
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Bem-vindo ao seu novo lembrete de eventos!\n\n"
        "Use /novo para criar um evento 📅\n"
        "Use /lista para ver seus eventos 📋"
    )

# ======================
# MAIN
# ======================

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # START command (must be before conversation handler)
    app.add_handler(CommandHandler("start", start))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("novo", novo)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_title)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_country)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city)],
            DATE: [CallbackQueryHandler(calendar_handler)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time)],
            RECURRENCE: [CallbackQueryHandler(set_recurrence)],
            EDIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_time)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CallbackQueryHandler(view_event, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(back_to_list, pattern="^back_to_list$"))
    app.add_handler(CallbackQueryHandler(edit_time, pattern="^edit_time$"))

    app.run_polling()

if __name__ == "__main__":
    main()
