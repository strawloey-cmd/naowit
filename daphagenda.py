import os
import sqlite3
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram_bot_calendar import DetailedTelegramCalendar

# ======================
# CONFIG
# ======================
TOKEN = os.getenv("TOKEN")
TITLE, COUNTRY, CITY, DATE, RECURRENCE = range(5)
NOTIFY_HOUR = 7  # Horário padrão das notificações

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
    await update.message.reply_text("🍰 Dê um nome ao seu evento:")
    return TITLE

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text
    await update.message.reply_text("🍨 Informe o país do evento:")
    return COUNTRY

async def set_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["country"] = update.message.text
    await update.message.reply_text("🍥 Informe a cidade do evento:")
    return CITY

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["city"] = update.message.text
    calendar, step = DetailedTelegramCalendar(firstweekday=6).build()
    await update.message.reply_text(
        "🍧 Selecione a data:",
        reply_markup=calendar
    )
    return DATE

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    result, key, step = DetailedTelegramCalendar(firstweekday=6).process(query.data)
    if not result and key:
        await query.edit_message_text("🎀 Selecione:", reply_markup=key)
        return DATE
    if result:
        context.user_data["datetime"] = result.isoformat()
        keyboard = [
            [
                InlineKeyboardButton("🧁 Uma vez", callback_data="once"),
                InlineKeyboardButton("🍪 Diário", callback_data="daily"),
                InlineKeyboardButton("🍬 Mensal", callback_data="monthly"),
            ]
        ]
        await query.edit_message_text(
            f"🎂 Data selecionada: {result.strftime('%d-%m-%Y')}\n\nEscolha a recorrência:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return RECURRENCE

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
    await query.edit_message_text("🫧 Evento criado com sucesso!")
    return ConversationHandler.END

# ======================
# MENU BUILDER
# ======================
def build_event_menu(user_id: int):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM reminders WHERE user_id = ?", (user_id,))
    events = cursor.fetchall()
    conn.close()
    if not events:
        return None
    keyboard = [[InlineKeyboardButton(title, callback_data=f"view_{event_id}")] for event_id, title in events]
    return InlineKeyboardMarkup(keyboard)

def build_delete_menu(user_id: int):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM reminders WHERE user_id = ?", (user_id,))
    events = cursor.fetchall()
    conn.close()
    if not events:
        return None
    keyboard = [[InlineKeyboardButton(title, callback_data=f"del_{event_id}")] for event_id, title in events]
    return InlineKeyboardMarkup(keyboard)

# ======================
# /LISTA
# ======================
async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = build_event_menu(update.effective_user.id)
    if not menu:
        await update.message.reply_text("Você não possui eventos.")
        return
    await update.message.reply_text("🧋 Seus eventos:", reply_markup=menu)

async def view_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.split("_")[1]
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, datetime, country, city, recurrence FROM reminders WHERE id = ?", (event_id,))
    event = cursor.fetchone()
    conn.close()
    title, dt_str, country, city, recurrence = event
    dt = datetime.fromisoformat(dt_str)
    recurrence_map = {"once": "Uma vez", "daily": "Diário", "monthly": "Mensal"}
    message = (
        f"🌸 Nome: {title}\n\n"
        f"🍩 Data: {dt.strftime('%d-%m-%Y')}\n"
        f"🧺 Local: {city}, {country}\n"
        f"🥨 Recorrência: {recurrence_map.get(recurrence)}"
    )
    keyboard = [[InlineKeyboardButton("🍭 Voltar", callback_data="back_to_list")]]
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    menu = build_event_menu(query.from_user.id)
    if not menu:
        await query.edit_message_text("Você não possui eventos.")
        return
    await query.edit_message_text("🧋 Seus eventos:", reply_markup=menu)

# ======================
# /DELETAR
# ======================
async def deletar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = build_delete_menu(update.effective_user.id)
    if not menu:
        await update.message.reply_text("Você não possui eventos para deletar.")
        return
    await update.message.reply_text("🥐 Selecione o evento que deseja deletar:", reply_markup=menu)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.split("_")[1]
    context.user_data["delete_id"] = event_id
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM reminders WHERE id = ?", (event_id,))
    title = cursor.fetchone()[0]
    conn.close()
    keyboard = [
        [InlineKeyboardButton("🥞 Confirmar", callback_data="delete_yes"),
         InlineKeyboardButton("🍦 Cancelar", callback_data="delete_no")]
    ]
    await query.edit_message_text(f"🍡 Tem certeza que deseja deletar o evento:\n\n🍙 {title} ?", reply_markup=InlineKeyboardMarkup(keyboard))

async def execute_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "delete_yes":
        event_id = context.user_data.get("delete_id")
        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("🥞 Evento deletado com sucesso!")
    else:
        await query.edit_message_text("🍦 Exclusão cancelada.")

# ======================
# /START
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Bem-vindo ao seu lembrete de eventos! 🎀\n\n"
        "🪞 /novo — Criar evento\n"
        "🩰 /lista — Ver eventos\n"
        "🦢 /deletar — Deletar evento"
    )

# ======================
# NOTIFICAÇÕES AUTOMÁTICAS
# ======================
async def check_events(context: ContextTypes.DEFAULT_TYPE):
    brasil_tz = pytz.timezone("America/Sao_Paulo")
    now = datetime.now(brasil_tz)

    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, datetime, recurrence FROM reminders")
    events = cursor.fetchall()
    conn.close()

    for event_id, user_id, title, dt_str, recurrence in events:
        dt = datetime.fromisoformat(dt_str)

        send_notification = False

        if recurrence == "once" and dt.date() == now.date() and now.hour == 7 and now.minute == 0:
            send_notification = True
        elif recurrence == "daily" and now.hour == 7 and now.minute == 0:
            send_notification = True
        elif recurrence == "monthly" and dt.day == now.day and now.hour == 7 and now.minute == 0:
            send_notification = True

        if send_notification:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🧸 Lembrete: {title} hoje!"
            )

# ======================
# MAIN
# ======================
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Start
    app.add_handler(CommandHandler("start", start))

    # Novo
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("novo", novo)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_title)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_country)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city)],
            DATE: [CallbackQueryHandler(calendar_handler)],
            RECURRENCE: [CallbackQueryHandler(set_recurrence, pattern="^(once|daily|monthly)$")],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)

    # Lista
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CallbackQueryHandler(view_event, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(back_to_list, pattern="^back_to_list$"))

    # Deletar
    app.add_handler(CommandHandler("deletar", deletar))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(execute_delete, pattern="^delete_"))

    # Ativa verificação automática a cada 60 segundos
    app.job_queue.run_repeating(check_events, interval=60, first=10)

    # Run
    app.run_polling()

if __name__ == "__main__":
    main()
