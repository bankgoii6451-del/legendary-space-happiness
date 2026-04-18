
import os
import logging
from io import BytesIO
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # ใส่ token ของบอทใน environment หรือ แทนตรงนี้
TARGET_CHAT = os.environ.get("TARGET_CHAT")  # ใส่ chat id หรือ @channelusername ที่จะให้บอทโพสต์
# ตัวอย่าง ADMIN_IDS: "12345678,87654321" (user ids ของผู้ที่อนุญาตให้สั่งโพสต์)
ADMIN_IDS = set(int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip())

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "สวัสดี! ใช้คำสั่ง /post เพื่อโพสต์รูป+ข้อความ\n\n"
        "ตัวอย่างการใช้งาน:\n"
        "1) แนบรูปมากับข้อความแล้วพิมพ์ /post <ข้อความแคปชั่น>\n"
        "2) /post <image_url> | <ข้อความแคปชั่น>\n\n"
        "หากต้องการให้โพสต์ไปที่ช่อง/แชทอื่น ให้ตั้ง TARGET_CHAT เป็น chat id หรือ @channelusername"
    )


def is_admin(user_id: int) -> bool:
    # ถ้า ADMIN_IDS ว่าง ให้อนุญาตทุกคน (เปลี่ยนตามต้องการ)
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    dest_chat = TARGET_CHAT or update.effective_chat.id

    # ถ้ามีรูปแนบมาพร้อมคำสั่ง (photo)
    if update.message.photo:
        # ถ้าผู้ใช้แนบรูปและส่งคำสั่ง, caption อาจอยู่ใน args หรือ message.caption
        caption = " ".join(context.args) if context.args else (update.message.caption or "")
        # ใช้ file_id ที่ Telegram เก็บไว้ (ง่ายและเร็ว)
        file_id = update.message.photo[-1].file_id
        try:
            await context.bot.send_photo(chat_id=dest_chat, photo=file_id, caption=caption)
            await update.message.reply_text("โพสต์รูปเรียบร้อยแล้ว ✅")
        except Exception as e:
            logger.exception("send_photo failed")
            await update.message.reply_text(f"เกิดข้อผิดพลาดในการโพสต์: {e}")
        return

    # ถ้าไม่มีรูปแนบ แต่ผู้ใช้ส่ง URL และ caption แบบ "url | caption"
    if context.args:
        raw = " ".join(context.args).strip()
        if "|" in raw:
            image_url, caption = map(str.strip, raw.split("|", 1))
            # ถ้า URL เป็นของภาพที่ Telegram รองรับ ส่งตรงได้, แต่บางกรณีต้องดาวน์โหลดแล้วส่งเป็นไฟล์
            try:
                # พยายามส่ง URL ตรง ๆ ก่อน
                await context.bot.send_photo(chat_id=dest_chat, photo=image_url, caption=caption)
                await update.message.reply_text("โพสต์รูปเรียบร้อยแล้ว ✅")
            except Exception:
                # ถ้าส่ง URL ตรงๆ ไม่ได้ ลองดาวน์โหลดแล้วส่งเป็นไฟล์
                try:
                    r = requests.get(image_url, timeout=15)
                    r.raise_for_status()
                    bio = BytesIO(r.content)
                    bio.name = "image.jpg"
                    bio.seek(0)
                    await context.bot.send_photo(chat_id=dest_chat, photo=bio, caption=caption)
                    await update.message.reply_text("โพสต์รูป (จากการดาวน์โหลด) เรียบร้อยแล้ว ✅")
                except Exception as e:
                    logger.exception("download or send failed")
                    await update.message.reply_text(f"เกิดข้อผิดพลาดในการดาวน์โหลด/โพสต์: {e}")
        else:
            await update.message.reply_text(
                "รูปแบบคำสั่งไม่ถูกต้อง\nใช้: /post <image_url> | <caption>\nหรือแนบรูปแล้วใช้ /post <caption>"
            )
        return

    # ถ้าไม่มีรูปหรือ args
    await update.message.reply_text(
        "ไม่พบรูปหรือ URL ที่จะโพสต์\nแนบรูปมาพร้อมคำสั่ง หรือใช้ /post <image_url> | <caption>"
    )


async def echo_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ถ้าต้องการให้บอทตอบเมื่อมีรูปที่ไม่ได้มาพร้อมคำสั่ง (optional)
    await update.message.reply_text("ระบบได้รับรูปแล้ว ถ้าต้องการให้โพสต์ไปที่เป้าหมาย ให้ส่งคำสั่ง /post ตามด้วยแคปชั่นหรือ URL ครับ")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("กรุณาตั้งค่า BOT_TOKEN ใน environment")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", post_command))
    # ถ้าต้องการจัดการข้อความรูปที่ไม่ได้มากับ /post
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, echo_photo))

    logger.info("Bot started (polling)...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
