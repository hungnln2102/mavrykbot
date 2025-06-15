
from telegram import Update
import os
import logging
from config import BOT_TOKEN, logger
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    AIORateLimiter
)

#Menu and Function Menu
from menu import show_outer_menu, show_main_selector
from add_order import add_order_conv, start_add, cancel_add
from delete_order import get_delete_order_conversation_handler, get_delete_callbacks, start_delete_order
from update_order import get_update_order_conversation_handler
from view_due_orders import view_expired_orders, show_expired_order, extend_order, delete_order_from_expired
from Payment_Supply import (
    handle_exit_to_main,
    handle_source_paid,
    handle_source_navigation,
    show_source_payment
)
from aiohttp import web
import asyncio
from payment_webhook import routes as sepay_routes


AUTHORIZED_USER_ID = 510811276

# Cấu hình log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ✅ Lấy token từ biến môi trường
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ TELEGRAM_TOKEN chưa được thiết lập!")

def user_only_filter(func):
    async def wrapper(update, context):
        user_id = update.effective_user.id
        if user_id != AUTHORIZED_USER_ID:
            if update.message:
                await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Bạn không có quyền dùng chức năng này.", show_alert=True)
            return
        return await func(update, context)
    return wrapper

@user_only_filter
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_outer_menu(update, context)

@user_only_filter
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == 'menu_shop':
        await show_main_selector(update, context, edit=True)
    elif query.data == 'menu_customer':
        await query.answer("📌 Phân hệ Khách Hàng sẽ được bổ sung sau.", show_alert=True)
    elif query.data == 'expired':
        await view_expired_orders(update, context)
    elif query.data == 'next_expired':
        await show_expired_order(update, context, direction="next")
    elif query.data == 'prev_expired':
        await show_expired_order(update, context, direction="prev")
    elif query.data == 'back_to_menu':
        await show_outer_menu(update, context)
    elif query.data == 'delete':
        await query.answer()  # 👉 Phản hồi để tránh lỗi
        return  # Không xử lý gì thêm, ConversationHandler sẽ tự lo

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Lỗi khi answer callback: {e}")

async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, bot=request.app["bot"])
    await request.app["application"].update_queue.put(update)
    return web.Response()

@user_only_filter
async def thanh_toan_nguon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_source_payment(update, context, index=0)

async def healthcheck(request):
    return web.Response(text="Bot is alive!")

async def main():
    application = Application.builder().token(BOT_TOKEN).rate_limiter(AIORateLimiter()).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(add_order_conv)
    application.add_handler(get_update_order_conversation_handler())
    application.add_handler(get_delete_order_conversation_handler())

    application.add_handler(CallbackQueryHandler(cancel_add, pattern="^cancel_add$"))
    application.add_handler(CallbackQueryHandler(start_add, pattern="^add$"))

    application.add_handler(CallbackQueryHandler(button_callback, pattern=r'^(menu_shop|menu_customer|expired|next_expired|prev_expired|back_to_menu|delete)$'))
    application.add_handler(CallbackQueryHandler(extend_order, pattern=r"^extend_order\|"))
    application.add_handler(CallbackQueryHandler(delete_order_from_expired, pattern=r"^delete_order\|"))
    application.add_handler(CallbackQueryHandler(show_expired_order, pattern=r"^next_expired$"))
    application.add_handler(CallbackQueryHandler(show_expired_order, pattern=r"^prev_expired$"))
    application.add_handler(CallbackQueryHandler(thanh_toan_nguon_handler, pattern='^payment_source$'))
    application.add_handler(CallbackQueryHandler(handle_exit_to_main, pattern="^exit_to_main$"))
    application.add_handler(CallbackQueryHandler(handle_source_paid, pattern="^source_paid\\|"))
    application.add_handler(CallbackQueryHandler(handle_source_navigation, pattern="^source_(next|prev)\\|"))

    for handler in get_delete_callbacks():
        application.add_handler(handler)

    await application.initialize()
    await application.start()
    bot = application.bot

    app = web.Application()
    app.add_routes(sepay_routes)
    app["application"] = application
    app["bot"] = bot
    app.router.add_get("/", healthcheck)
    app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()
    logger.info("✅ Bot đã khởi động bằng webhook.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

