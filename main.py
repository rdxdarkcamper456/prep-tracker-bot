import sqlite3
import os
from datetime import date
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- FLASK WEB SERVER (Render Port Binding ke liye) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is running live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

# --- BOT TOKEN ---
BOT_TOKEN = "8929714993:AAHc0ve1genzBeboUZGQs2WtskX8uL_BEj0"

# --- DATABASE SETUP ---
conn = sqlite3.connect('tracker.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS prep_logs (
        user_id INTEGER,
        name TEXT,
        entry_date TEXT,
        physics INTEGER,
        chemistry INTEGER,
        biology INTEGER
    )
''')
conn.commit()

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **Welcome to Prep Tracker Bot!**\n\n"
        "Daily progress log karne ke liye:\n"
        "`/add <Physics> <Chemistry> <Biology>`\n"
        "Example: `/add 20 30 25`\n\n"
        "Past history dekhne ke liye:\n"
        "`/myhistory`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = str(date.today())
    
    if len(context.args) != 3:
        await update.message.reply_text(
            "⚠️ **Incorrect Format!**\n"
            "Format: `/add <Physics> <Chemistry> <Biology>`\n"
            "Example: `/add 20 30 25`"
        )
        return

    try:
        phy = int(context.args[0])
        chem = int(context.args[1])
        bio = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Sirf numbers enter karein!")
        return

    cursor.execute('''
        INSERT INTO prep_logs (user_id, name, entry_date, physics, chemistry, biology)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user.id, user.first_name, today, phy, chem, bio))
    conn.commit()

    total = phy + chem + bio
    await update.message.reply_text(
        f"✅ **Entry Saved! ({today})**\n\n"
        f"⚛️ Physics: {phy}\n"
        f"🧪 Chemistry: {chem}\n"
        f"🧬 Biology: {bio}\n"
        f"📊 Total: {total} Questions"
    )

async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute('''
        SELECT entry_date, physics, chemistry, biology 
        FROM prep_logs 
        WHERE user_id = ? 
        ORDER BY entry_date DESC LIMIT 7
    ''', (user.id,))
    
    records = cursor.fetchall()
    
    if not records:
        await update.message.reply_text("❌ Aapka abhi tak koi record nahi mila.")
        return

    msg = f"📅 **{user.first_name}'s Last 7 Entries:**\n\n"
    for row in records:
        day_total = row[1] + row[2] + row[3]
        msg += f"🗓 **{row[0]}** → P: {row[1]} | C: {row[2]} | B: {row[3]} | Total: {day_total}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

def main():
    # Flask server ko background thread me chalayein
    Thread(target=run_flask).start()

    # Telegram Bot Start
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_entry))
    app.add_handler(CommandHandler("myhistory", view_history))

    print("Bot chalu ho gaya hai...")
    app.run_polling()

if __name__ == '__main__':
    main()
