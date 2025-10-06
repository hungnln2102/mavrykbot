import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from menu import show_outer_menu
from utils import append_to_sheet
from column import SHEETS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)
GET_ORDER_ID, GET_AMOUNT = range(2)

async def start_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data='cancel_refund')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="💸 **QUY TRÌNH HOÀN TIỀN** 💸\n\n"
             "Vui lòng nhập **Mã Đơn Hàng** cần hoàn tiền.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    context.user_data['refund_message_id'] = query.message.message_id
    
    return GET_ORDER_ID

async def handle_order_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_id = update.message.text
    context.user_data['refund_order_id'] = order_id
    logger.info(f"Refund - Order ID: {order_id}")
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data='cancel_refund')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.delete()
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('refund_message_id'),
        text=f"✅ Đã ghi nhận mã đơn: `{order_id}`\n\n"
             f"Bây giờ, vui lòng nhập **Số Tiền** cần hoàn.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return GET_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text
    try:
        sanitized_text = amount_text.strip().replace(',', '.')
        numeric_value = float(sanitized_text)
        final_amount = numeric_value * 1000
    except ValueError:
        keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data='cancel_refund')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('refund_message_id'),
            text="❌ Số tiền không hợp lệ. Vui lòng chỉ nhập số (có thể chứa dấu `.` hoặc `,`).\n\n"
                 "Hãy thử lại hoặc bấm nút Hủy bên dưới.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        await update.message.delete()
        return GET_AMOUNT

    order_id = context.user_data.get('refund_order_id')
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    formatted_date = now.strftime("%d/%m/%Y %H:%M:%S")
    try:
        append_to_sheet(SHEETS["REFUND"], [order_id, formatted_date, final_amount])
    except Exception as e:
        logger.error(f"Lỗi khi thực thi append_to_sheet trong refund: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('refund_message_id'),
            text=f"❌ Đã xảy ra lỗi khi cố gắng ghi vào Google Sheet. Vui lòng kiểm tra lại cấu hình và file log.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END
    await update.message.delete()
    display_amount = f"{int(final_amount):,}"
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('refund_message_id'),
        text="✅ **THÀNH CÔNG!**\n\n"
             "Đã lưu thông tin hoàn tiền:\n"
             f"  - Mã Đơn Hàng: `{order_id}`\n"
             f"  - Số Tiền đã xử lý: `{display_amount}`\n"
             f"  - Thời Gian: `{formatted_date}`\n\n"
             "_Sẽ tự động quay về menu chính sau vài giây..._",
        parse_mode='Markdown'
    )
    context.user_data.clear()
    await asyncio.sleep(3)
    await show_outer_menu(update, context)
    return ConversationHandler.END

async def cancel_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    logger.info("User cancelled the refund process.")
    await show_outer_menu(update, context)
    return ConversationHandler.END

def get_refund_conversation_handler() -> ConversationHandler:
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_refund, pattern="^start_refund$")],
        states={
            GET_ORDER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_id)],
            GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
        },
        fallbacks=[CallbackQueryHandler(cancel_refund, pattern='^cancel_refund$')],
        per_message=False,
        allow_reentry=True
    )
    return conv_handler