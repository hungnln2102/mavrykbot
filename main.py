# main.py (Đã sửa đổi hoàn chỉnh)

from telegram import Update
import os
import logging
import datetime  # <<< THÊM MỚI
import pytz      # <<< THÊM MỚI
from config import BOT_TOKEN, logger
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    AIORateLimiter
)

from menu import show_outer_menu, show_main_selector
from create_qrcode import qr_conversation
from add_order import get_add_order_conversation_handler, start_add, cancel_add
from update_order import get_update_order_conversation_handler
from refund import get_refund_conversation_handler
from import_order import get_import_order_conversation_handler
from error_handler import error_handler
from View_order_unpaid import (
    view_unpaid_orders,
    show_unpaid_order,
    delete_unpaid_order,
    mark_paid_unpaid_order,
    exit_unpaid
)

# === THAY ĐỔI 1: Chỉ import hàm job mới ===
from view_due_orders import check_due_orders_job 
# (Các hàm cũ như view_expired_orders, extend_order... đã bị xóa khỏi import)

from Payment_Supply import (
    handle_exit_to_main,
    handle_source_paid,
    handle_source_navigation,
    show_source_payment
)
from aiohttp import web
import asyncio
from payment_webhook import routes as sepay_routes


AUTHORIZED_USER_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ TELEGRAM_TOKEN chưa được thiết lập!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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
    await query.answer()
    if query.data == 'menu_shop':
        await show_main_selector(update, context, edit=True)
    elif query.data == 'unpaid_orders':
        await view_unpaid_orders(update, context)
    # elif query.data == 'expired': # <<< ĐÃ XÓA
    #     await view_expired_orders(update, context)
    elif query.data == 'back_to_menu':
        await show_outer_menu(update, context)
    elif query.data == 'delete':
        return

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

async def payment_notify(request):
    token = request.match_info.get('token')
    try:
        data = await request.json()
    except Exception:
        data = {"error": "Không parse được JSON"}
    logger.info(f"📩 Bank webhook nhận được (token={token}): {data}")
    return web.Response(text="OK", status=200)


async def main():
    application = Application.builder().token(BOT_TOKEN).rate_limiter(AIORateLimiter()).build()

    # === THAY ĐỔI 2: Lên lịch cho Job chạy lúc 7:00 sáng ===
    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    run_time = datetime.time(hour=7, minute=0, tzinfo=vn_timezone)
    
    job_queue = application.job_queue
    job_queue.run_daily(
        check_due_orders_job,
        time=run_time,
        job_kwargs={'misfire_grace_time': 3600} # Chạy nếu bot bị lỡ giờ (trong 1h)
    )
    logger.info(f"Đã lên lịch quét đơn hết hạn hàng ngày lúc 07:00 sáng (Giờ VN).")
    # ====================================================

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(get_refund_conversation_handler())
    application.add_handler(get_add_order_conversation_handler())
    application.add_handler(get_update_order_conversation_handler())
    application.add_handler(qr_conversation)
    application.add_handler(get_import_order_conversation_handler())

    # === THAY ĐỔI 3: Xóa 'expired' khỏi handler này ===
    application.add_handler(CallbackQueryHandler(button_callback, pattern=r'^(menu_shop|back_to_menu|delete)$'))

    # === THAY ĐỔI 4: Xóa toàn bộ handler của "expired" ===
    # application.add_handler(CallbackQueryHandler(lambda u, c: show_expired_order(u, c, "next"), pattern=r"^next_expired$"))
    # application.add_handler(CallbackQueryHandler(lambda u, c: show_expired_order(u, c, "prev"), pattern=r"^prev_expired$"))
    # application.add_handler(CallbackQueryHandler(extend_order, pattern=r"^extend_order\|"))
    # application.add_handler(CallbackQueryHandler(delete_order_from_expired, pattern=r"^delete_order_from_expired\|"))
    # application.add_handler(CallbackQueryHandler(back_to_menu_from_expired, pattern=r"^back_to_menu_expired$"))
    # =================================================

    application.add_handler(get_add_order_conversation_handler()) # Dòng này bị lặp, nhưng không sao
    application.add_handler(CallbackQueryHandler(thanh_toan_nguon_handler, pattern='^payment_source$'))
    application.add_handler(CallbackQueryHandler(handle_exit_to_main, pattern="^exit_to_main$"))
    application.add_handler(CallbackQueryHandler(handle_source_paid, pattern="^source_paid\\|"))
    application.add_handler(CallbackQueryHandler(handle_source_navigation, pattern="^source_(next|prev)\\|"))
    application.add_handler(CallbackQueryHandler(view_unpaid_orders, pattern="^unpaid_orders$"))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_unpaid_order(u, c, "next"), pattern="^next_unpaid$"))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_unpaid_order(u, c, "prev"), pattern="^prev_unpaid$"))
    application.add_handler(CallbackQueryHandler(delete_unpaid_order, pattern="^delete_unpaid\\|"))
    application.add_handler(CallbackQueryHandler(mark_paid_unpaid_order, pattern="^paid_unpaid\\|"))
    application.add_handler(CallbackQueryHandler(exit_unpaid, pattern="^exit_unpaid$"))
    
    application.add_error_handler(error_handler)
    await application.initialize()
    await application.start()

    if WEBHOOK_URL:
        logger.info(f"Bắt đầu thiết lập webhook tới: {WEBHOOK_URL}")
        await application.bot.set_webhook(url=WEBHOOK_URL)
        webhook_info = await application.bot.get_webhook_info()
        if webhook_info.url == WEBHOOK_URL:
            logger.info("✅ Webhook Telegram đã được thiết lập thành công!")
        else:
            logger.error(f"❌ Thiết lập webhook Telegram thất bại. Telegram trả về URL: {webhook_info.url}")
    else:
        logger.warning("⚠️ Chưa đặt biến môi trường WEBHOOK_URL, bot sẽ không nhận qua webhook.")

    bot = application.bot
    app = web.Application()
    app.add_routes(sepay_routes)
    app["application"] = application
    app["bot"] = bot
    app.router.add_get("/", healthcheck)
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_post("/api/payment/notify/{token}", payment_notify)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port=8080)
    await site.start()
    logger.info("✅ Bot đã khởi động và sẵn sàng nhận yêu cầu.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())