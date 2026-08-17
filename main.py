import os
import re
import asyncio
from datetime import date, timedelta, datetime
from aiohttp import web
import psycopg2
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# --- BOT & DB CONFIG ---
BOT_TOKEN = "8929714993:AAHc0ve1genzBeboUZGQs2WtskX8uL_BEj0"
# Yahan Supabase se copy kiya hua URI paste karein:
SUPABASE_DB_URI = SUPABASE_DB_URI = "postgresql://postgres.kpmrmrrxucjzhhnfzsnf:@MyPrepTracker_bot2@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

# --- DATABASE SETUP (SUPABASE) ---
def get_db_connection():
    return psycopg2.connect(SUPABASE_DB_URI)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prep_logs (
            user_id BIGINT,
            name TEXT,
            entry_date DATE,
            physics INT,
            chemistry INT,
            biology INT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_goals (
            user_id BIGINT PRIMARY KEY,
            daily_goal INT DEFAULT 100
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# Initialize tables
init_db()

# --- WEB SERVER FOR RENDER ---
async def handle_ping(request):
    return web.Response(text="Bot is online with Supabase DB!")

# --- HELPER FUNCTIONS ---
def get_user_streak(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT entry_date FROM prep_logs 
        WHERE user_id = %s ORDER BY entry_date DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return 0
        
    dates = [row[0] for row in rows]
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
        today = date.today()
        
        phy = int(phy_match.group(1)) if phy_match else 0
        chem = int(chem_match.group(1)) if chem_match else 0
        bio = int(bio_match.group(1)) if bio_match else 0
        total = phy + chem + bio

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prep_logs (user_id, name, entry_date, physics, chemistry, biology)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (user.id, user.first_name, today, phy, chem, bio))
        
        cursor.execute('SELECT daily_goal FROM user_goals WHERE user_id = %s', (user.id,))
        goal_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        goal = goal_row[0] if goal_row else 100
        percentage = min(int((total / goal) * 100), 100)
        filled_blocks = int(percentage / 10)
        bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

        formatted_date = today.strftime("%d %b")
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
        "👋 **Prep Tracker Bot Started! (Cloud Powered ☁️)**\n\n"
        "**Commands:**\n"
        "• Send text: `Physics 20 Chemistry 30 Biology 25`\n"
        "• `/me` — View stats & streak\n"
        "• `/history` — View past logs\n"
        "• `/leaderboard` — View ranking\n"
        "• `/goal 100` — Set target"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = date.today()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(physics), SUM(chemistry), SUM(biology)
        FROM prep_logs WHERE user_id = %s AND entry_date = %s
    ''', (user.id, today))
    today_data = cursor.fetchone()
    
    phy_t = today_data[0] or 0
    chem_t = today_data[1] or 0
    bio_t = today_data[2] or 0
    today_total = phy_t + chem_t + bio_t

    cursor.execute('''
        SELECT SUM(physics + chemistry + biology)
        FROM prep_logs WHERE user_id = %s
    ''', (user.id,))
    total_all = cursor.fetchone()[0] or 0
    cursor.close()
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT entry_date, SUM(physics), SUM(chemistry), SUM(biology)
        FROM prep_logs WHERE user_id = %s
        GROUP BY entry_date ORDER BY entry_date DESC LIMIT 7
    ''', (user.id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Aapka koi history record nahi mila.")
        return

    msg = f"📜 **Your Practice History (Last 7 Days)**\n\n"
    for r in rows:
        dt = r[0].strftime("%d %b")
        p, c, b = r[1] or 0, r[2] or 0, r[3] or 0
        tot = p + c + b
        msg += f"🗓 **{dt}** → P:{p} C:{c} B:{b} → **{tot} Q**\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seven_days_ago = date.today() - timedelta(days=7)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, SUM(physics + chemistry + biology) as total
        FROM prep_logs
        WHERE entry_date >= %s
        GROUP BY user_id, name
        ORDER BY total DESC LIMIT 10
    ''', (seven_days_ago,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

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
        await update.message.reply_text("⚠️ Target number me set karein: `/goal 100`")
        return

    target = int(context.args[0])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_goals (user_id, daily_goal) VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET daily_goal = EXCLUDED.daily_goal
    ''', (user.id, target))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text(f"🎯 Target set to **{target} questions/day**!")

async def main():
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("me", my_stats))
    bot_app.add_handler(CommandHandler("history", history))
    bot_app.add_handler(CommandHandler("leaderboard", leaderboard))
    bot_app.add_handler(CommandHandler("goal", set_goal))

    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_natural_text))

    web_app = web.Application()
    web_app.router.add_get('/', handle_ping)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
