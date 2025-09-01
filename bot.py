from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ContextTypes
from datetime import datetime, timedelta
from flask import Flask, request
import threading
import sqlite3
import os

# 🔐 توكن البوت و ID المدير من environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8299040467:AAEoaANNGdI72HbkPiqVDVbm9tcerWcughs")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1489673093))

# 🗂 مسار قاعدة بيانات SQLite
DB_PATH = "/data/bot.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS codes (
                        code TEXT PRIMARY KEY,
                        added TEXT,
                        used INTEGER
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS allowed_users (
                        user_id INTEGER PRIMARY KEY
                     )''')
        c.execute("INSERT OR IGNORE INTO allowed_users (user_id) VALUES (?)", (ADMIN_ID,))

if not os.path.exists(DB_PATH):
    init_db()

# إنشاء تطبيق Flask
flask_app = Flask(__name__)

# ======================
# 🔹 دوال مساعدة
# ======================
def get_codes():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT code, added, used FROM codes")
        codes = {row[0]: {"added": datetime.fromisoformat(row[1]), "used": bool(row[2])} for row in c.fetchall()}
    return codes

def clean_old_codes():
    """حذف الرموز التي مر عليها أكثر من 60 يومًا (الحفظ لمدة 60 يوم)"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        threshold = datetime.now() - timedelta(days=60)
        c.execute("DELETE FROM codes WHERE datetime(added) < ?", (threshold.isoformat(),))
        conn.commit()

def get_allowed_users():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM allowed_users")
        users = {row[0] for row in c.fetchall()}
    return users

def add_code(code):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO codes (code, added, used) VALUES (?, ?, ?)",
                  (code, datetime.now().isoformat(), 0))
        conn.commit()

def delete_code(code):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM codes WHERE code = ?", (code,))
        conn.commit()

def use_code(code):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE codes SET used = 1 WHERE code = ?", (code,))
        conn.commit()

def manage_user(user_id, add=True):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if add:
            c.execute("INSERT OR IGNORE INTO allowed_users (user_id) VALUES (?)", (user_id,))
        else:
            c.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
        conn.commit()

def get_code_status(code_data):
    """ترجع حالة الرمز والأيام المتبقية (صلاحية 30 يومًا فقط)"""
    added_date = code_data["added"]
    used = code_data["used"]
    days_passed = (datetime.now() - added_date).days
    days_left = max(0, 30 - days_passed)  # صلاحية 30 يومًا
    if used:
        return f"❌ مستخدم - انتهى"
    elif days_left <= 0:
        return f"❌ منتهي"
    else:
        return f"✅ فعال - باقي {days_left} يوم"

def get_status_emoji(status):
    if "✅" in status:
        return "✅"
    elif "❌" in status:
        return "❌"
    return ""

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_allowed(user_id):
    return user_id in get_allowed_users()

# ======================
# 🔹 لوحة المدير
# ======================
def admin_menu():
    buttons = [
        [InlineKeyboardButton("➕ إضافة رمز", callback_data="add_code")],
        [InlineKeyboardButton("🗑️ حذف رمز", callback_data="delete_code")],
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="manage_users")],
        [InlineKeyboardButton("📜 عرض الرموز", callback_data="list_codes")],
        [InlineKeyboardButton("🔍 تحقق من رمز", callback_data="check_code")]
    ]
    return InlineKeyboardMarkup(buttons)

# 🔹 لوحة المستخدم/المشرف
def user_menu():
    buttons = [
        [InlineKeyboardButton("🔍 تحقق من رمز", callback_data="check_code")],
        [InlineKeyboardButton("📜 عرض الرموز", callback_data="list_codes")]
    ]
    return InlineKeyboardMarkup(buttons)

# ======================
# 🔹 الأوامر الأساسية
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clean_old_codes()  # تنظيف الرموز بعد 60 يومًا
    if not is_allowed(user_id):
        await update.message.reply_text("🚫 ليس لديك صلاحية الدخول. تواصل مع المدير.")
        return
    if is_admin(user_id):
        await update.message.reply_text("👑 أهلاً بك أيها المدير", reply_markup=admin_menu())
    else:
        await update.message.reply_text("✅ أهلاً بك", reply_markup=user_menu())

# ======================
# 🔹 ردود الأزرار
# ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "add_code" and is_admin(user_id):
        await query.message.reply_text("✏️ أرسل الرمز الجديد:")
        context.user_data["action"] = "add_code"

    elif data == "delete_code" and is_admin(user_id):
        await query.message.reply_text("🗑️ أرسل الرمز الذي تريد حذفه:")
        context.user_data["action"] = "delete_code"

    elif data == "manage_users" and is_admin(user_id):
        await query.message.reply_text("👥 أرسل ID المستخدم لتفعيل/إلغاء صلاحية:")
        context.user_data["action"] = "manage_users"

    elif data == "check_code" and is_allowed(user_id):
        await query.message.reply_text("🔍 أرسل الرمز للتحقق منه:")
        context.user_data["action"] = "check_code"

    elif data == "list_codes" and is_allowed(user_id):
        clean_old_codes()  # تنظيف الرموز بعد 60 يومًا
        text = "📜 قائمة الرموز:\n"
        codes = get_codes()
        if not codes:
            text += "لا يوجد رموز حالياً"
        else:
            for code, data in codes.items():
                status = get_code_status(data)
                text += f"- {code}: {status}\n"
        await query.message.reply_text(text)

    elif data.startswith("use_code:") and is_allowed(user_id):
        code = data.split(":", 1)[1]
        codes = get_codes()
        if code in codes and not codes[code]["used"]:
            days_passed = (datetime.now() - codes[code]["added"]).days
            if days_passed < 30:  # صلاحية 30 يومًا
                use_code(code)
                await query.edit_message_text(f"✅ تم استخدام الرمز: {code}")
            else:
                await query.edit_message_text(f"❌ الرمز {code} منتهي الصلاحية")
        else:
            await query.edit_message_text(f"⚠️ الرمز {code} غير صالح أو مستخدم بالفعل")

    elif data.startswith("cancel_code:") and is_allowed(user_id):
        code = data.split(":", 1)[1]
        await query.edit_message_text(f"🚫 تم إلغاء العملية للرمز: {code}")

    elif data.startswith("back_code:") and is_allowed(user_id):
        code = data.split(":", 1)[1]
        codes = get_codes()
        status = get_code_status(codes.get(code, {}))
        await query.edit_message_text(f"الرمز {code}: {status}")

# ======================
# 🔹 معالجة الرسائل
# ======================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    action = context.user_data.get("action")

    if not action:
        return

    if action == "add_code" and is_admin(user_id):
        add_code(text)
        await update.message.reply_text(f"✅ تم إضافة الرمز: {text}")
    
    elif action == "delete_code" and is_admin(user_id):
        codes = get_codes()
        if text in codes:
            delete_code(text)
            await update.message.reply_text(f"🗑️ تم حذف الرمز: {text}")
        else:
            await update.message.reply_text("⚠️ الرمز غير موجود")
    
    elif action == "manage_users" and is_admin(user_id):
        try:
            uid = int(text)
            if uid in get_allowed_users():
                manage_user(uid, add=False)
                await update.message.reply_text(f"🚫 تم إلغاء صلاحية: {uid}")
            else:
                manage_user(uid, add=True)
                await update.message.reply_text(f"✅ تم منح صلاحية: {uid}")
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال ID صالح (رقمي فقط)")
    
    elif action == "check_code" and is_allowed(user_id):
        codes = get_codes()
        if text in codes:
            code_data = codes[text]
            status = get_code_status(code_data)
            emoji = get_status_emoji(status)
            
            if "✅" in status:
                buttons = [
                    [InlineKeyboardButton(f"✅ استخدام", callback_data=f"use_code:{text}")],
                    [InlineKeyboardButton("🚫 إلغاء", callback_data=f"cancel_code:{text}")],
                    [InlineKeyboardButton("🔙 عودة", callback_data=f"back_code:{text}")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                await update.message.reply_text(f"الرمز {text}: {status}", reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"الرمز {text}: {status}")
        else:
            await update.message.reply_text("⚠️ الرمز غير موجود")

    context.user_data["action"] = None

# ======================
# 🔹 إعداد Webhook
# ======================
async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await application.process_update(update)

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    if update:
        threading.Thread(target=webhook_update, args=(update, application)).start()
    return "OK", 200

# ======================
# 🔹 تشغيل البوت
# ======================
def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(Filters.TEXT & ~Filters.COMMAND, message_handler))
    
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL', 'your-render-app.onrender.com')}/{BOT_TOKEN}"
    application.bot.set_webhook(url=webhook_url)
    
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

if __name__ == "__main__":
    main()
