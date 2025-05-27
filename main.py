from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import BOT_TOKEN, logger
from view_due_orders import view_expired_orders, show_expired_order
from menu import show_outer_menu, show_main_selector
from add_order import add_order_conv, start_add, cancel_add
from delete_order import get_delete_order_conversation_handler, get_delete_callbacks, start_delete_order
import asyncio
from aiohttp import web

AUTHORIZED_USER_ID = 510811276

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
    print(f"[START] User ID: {update.effective_user.id}")
    await show_outer_menu(update, context)

@user_only_filter
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    print("🔁 Callback nhận được:", query.data)

    if query.data == 'menu_shop':
        await show_main_selector(update, context)

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

    elif query.data == 'update':
        await query.answer("📌 Chức năng Cập Nhật Đơn sẽ được bổ sung sau.", show_alert=True)

    elif query.data == 'delete':
        return await start_delete_order(update, context)

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Lỗi khi answer callback: {e}")

async def healthcheck(request):
    return web.Response(text="Bot is alive!")

async def start():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(add_order_conv)
    app.add_handler(CallbackQueryHandler(cancel_add, pattern="^cancel_add$"))
    app.add_handler(CallbackQueryHandler(start_add, pattern="^add$"))
    app.add_handler(CallbackQueryHandler(button_callback,
        pattern='^(menu_shop|menu_customer|expired|next_expired|prev_expired|back_to_menu|update|delete)$'
    ))
    app.add_handler(get_delete_order_conversation_handler())
    for handler in get_delete_callbacks():
        app.add_handler(handler)

    logger.info("🤖 Bot đã bắt đầu chạy...")

    # Tạo web server nhỏ (port 8080)
    aio_app = web.Application()
    aio_app.router.add_get("/", healthcheck)

    # Chạy bot và server song song
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(start())
