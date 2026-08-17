import sqlite3
import os
import re
import asyncio
from datetime import date, timedelta, datetime
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# --- FLASK SERVER FOR RENDER ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Prep Tracker Bot is Active!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

# --- BOT CONFIG ---
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

cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_goals (
        user_id INTEGER PRIMARY KEY,
        daily_goal INTEGER DEFAULT 100
    )
''')
conn.commit()

# --- HELPER FUNCTIONS ---
def get_user_streak(user_id):
    cursor.execute('''
        SELECT DISTINCT entry_date FROM prep_logs 
        WHERE user_id = ? ORDER BY entry_date DESC
    ''', (user_id,))
    dates = [datetime.strptime(row[0], "%Y-%m-%d").date() for row in cursor.fetchall()]
    
    if not dates:
        return 0
        
    today = date.today()
    if dates[0] != today and dates[0] != today - timedelta(days=1):
        return 0
        
    streak = 1
    for i in range(len(dates) - 1):
        if dates[i] - dates[i+1] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak

# --- AUTOMATIC TEXT ENTRY HANDLER ---
async def handle_natural_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    phy_match = re.search(r'physics\s*[:=\-]?\s*(\d+)', text, re.IGNORECASE)
    chem_match = re.search(r'chemistry\s*[:=\-]?\s*(\d+)', text, re.IGNORECASE)
    bio_match = re.search(r'biology\s*[:=\-]?\s*(\d+)', text, re.IGNORECASE)

    if phy_match or chem_match or bio_match:
        user = update.effective_user
        today = str(date.today())
        
        phy = int(phy_match.group(1)) if phy_match else 0
        chem = int(chem_match.group(1)) if chem_match else 0
        bio = int(bio_match.group(1)) if bio_match else 0
        total = phy + chem + bio

        cursor.execute('''
            INSERT INTO prep_logs (user_id, name, entry_date, physics, chemistry, biology)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user.id, user.first_name, today, phy, chem, bio))
        conn.commit()

        cursor.execute('SELECT daily_goal FROM user_goals WHERE user_id = ?', (user.id,))
        goal_row = cursor.fetchone()
        goal = goal_row[0] if goal_row else 100
        
        percentage = min(int((total / goal) * 100), 100)
        filled_blocks = int(percentage / 10)
        bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

        formatted_date = date.today().strftime("%d %b")
        reply_msg = (
            f"✅ **Recorded for {user.first_name}!**\n\n"
            f"📅 **Date:** {formatted_date}\n"
            f"📚 Physics: {phy}\n"
            f"🧪 Chemistry: {chem}\n"
            f"🧬 Biology: {bio}\n"
            f"📊 **Total:** {total} Qs\n\n"
            f"🎯 **Today's Goal ({percentage}%):**\n"
            f"`{bar}` {total}/{goal}"
        )
        await update.message.reply_text(reply_msg, parse_mode="Markdown")

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 **Prep Tracker Bot Started!**\n\n"
        "**Features & Commands:**\n"
        "• Just send text like:\n"
        "  `Physics 20`\n"
        "  `Chemistry 30`\n"
        "  `Biology 25`\n\n"
        "• `/me` — View your detailed stats & streak\n"
        "• `/history` — View past practice logs\n"
        "• `/leaderboard` — View group ranking\n"
        "• `/goal 100` — Set your daily target\n"
        "• `/physics`, `/chemistry`, `/biology` — Subject history"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = str(date.today())
    
    cursor.execute('''
        SELECT SUM(physics), SUM(chemistry), SUM(biology)
        FROM prep_logs WHERE user_id = ? AND entry_date = ?
    ''', (user.id, today))
    today_data = cursor.fetchone()
    
    phy_t = today_data[0] or 0
    chem_t = today_data[1] or 0
    bio_t = today_data[2] or 0
    today_total = phy_t + chem_t + bio_t

    cursor.execute('''
        SELECT SUM(physics + chemistry + biology)
        FROM prep_logs WHERE user_id = ?
    ''', (user.id,))
    total_all = cursor.fetchone()[0] or 0

    streak = get_user_streak(user.id)

    msg = (
        f"📊 **{user.first_name}'s Study Stats**\n\n"
        f"📅 **Today:** {today_total} questions\n"
        f"📚 Physics: {phy_t}\n"
        f"🧪 Chemistry: {chem_t}\n"
        f"🧬 Biology: {bio_t}\n\n"
        f"🔥 **Current streak:** {streak} days\n"
        f"📈 **Total questions:** {total_all:,}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute('''
        SELECT entry_date, SUM(physics), SUM(chemistry), SUM(biology)
        FROM prep_logs WHERE user_id = ?
        GROUP BY entry_date ORDER BY entry_date DESC LIMIT 7
    ''', (user.id,))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("❌ Aapka koi history record nahi mila.")
        return

    msg = f"📜 **Your Practice History (Last 7 Days)**\n\n"
    for r in rows:
        dt = datetime.strptime(r[0], "%Y-%m-%d").strftime("%d %b")
        p, c, b = r[1] or 0, r[2] or 0, r[3] or 0
        tot = p + c + b
        msg += f"🗓 **{dt}** → P:{p} C:{c} B:{b} → **{tot} Q**\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seven_days_ago = str(date.today() - timedelta(days=7))
    cursor.execute('''
        SELECT name, SUM(physics + chemistry + biology) as total
        FROM prep_logs
        WHERE entry_date >= ?
        GROUP BY user_id
        ORDER BY total DESC LIMIT 10
    ''', (seven_days_ago,))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("🏆 Abhi tak leaderboard me koi entries nahi hain.")
        return

    medals = ["🥇", "🥈", "🥉"]
    msg = "🏆 **Weekly Leaderboard**\n\n"
    group_total = 0

    for idx, (name, total) in enumerate(rows):
        rank = medals[idx] if idx < 3 else f"{idx+1}."
        msg += f"{rank} **{name}** — {total:,} Q\n"
        group_total += total

    msg += f"\n👥 **Total Group Practice:** {group_total:,} Q"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ Direct target numeric me set karein. Example: `/goal 100`")
        return

    target = int(context.args[0])
    cursor.execute('''
        INSERT OR REPLACE INTO user_goals (user_id, daily_goal) VALUES (?, ?)
    ''', (user.id, target))
    conn.commit()

    await update.message.reply_text(f"🎯 Target set to **{target} questions/day**!")

async def subject_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cmd = update.message.text.replace('/', '').lower()
    
    col_map = {'physics': 'physics', 'chemistry': 'chemistry', 'biology': 'biology'}
    col = col_map.get(cmd, 'physics')
    
    cursor.execute(f'''
        SELECT entry_date, SUM({col}) FROM prep_logs 
        WHERE user_id = ? GROUP BY entry_date ORDER BY entry_date DESC LIMIT 7
    ''', (user.id,))
    rows = cursor.fetchall()

    msg = f"📊 **Subject History: {col.capitalize()}**\n\n"
    for r in rows:
        dt = datetime.strptime(r[0], "%Y-%m-%d").strftime("%d %b")
        msg += f"🗓 {dt} → **{r[1]} Q**\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

def main():
    # 1. Start Flask web server in a background thread
    Thread(target=run_flask, daemon=True).start()

    # 2. Build & Run Telegram Bot Application
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("me", my_stats))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("goal", set_goal))
    
    app.add_handler(CommandHandler("physics", subject_history))
    app.add_handler(CommandHandler("chemistry", subject_history))
    app.add_handler(CommandHandler("biology", subject_history))

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_natural_text))

    print("Bot polling started...")
    app.run_polling()

if __name__ == '__main__':
    main()
