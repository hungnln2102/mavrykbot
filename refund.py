# refund.py

import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Import các hàm cần thiết từ các file khác trong dự án của bạn
from menu import show_outer_menu
from utils import append_to_sheet
from column import SHEETS

# Cấu hình logging
logger = logging.getLogger(__name__)

# Các trạng thái của cuộc hội thoại
GET_ORDER_ID, GET_AMOUNT = range(2)

async def start_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu quy trình, yêu cầu mã đơn hàng và hiển thị nút Hủy."""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("❌ Hủy và quay lại", callback_data='cancel_refund')]]
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
    """Lưu mã đơn hàng và yêu cầu số tiền."""
    order_id = update.message.text
    context.user_data['refund_order_id'] = order_id
    logger.info(f"Refund - Order ID: {order_id}")

    await update.message.delete()

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('refund_message_id'),
        text=f"✅ Đã ghi nhận mã đơn: `{order_id}`\n\n"
             f"Bây giờ, vui lòng nhập **Số Tiền** cần hoàn.",
        reply_markup=None, # Xóa nút bấm sau khi qua bước này
        parse_mode='Markdown'
    )
    return GET_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lưu số tiền, ghi vào sheet, thông báo và tự động quay về menu."""
    amount_text = update.message.text
    try:
        # Chuyển đổi số tiền, loại bỏ dấu phẩy hoặc chấm
        amount = float(amount_text.replace(',', '').replace('.', ''))
    except ValueError:
        # Nếu nhập sai, yêu cầu nhập lại và hiện lại nút Hủy
        keyboard = [[InlineKeyboardButton("❌ Hủy và quay lại", callback_data='cancel_refund')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('refund_message_id'),
            text="❌ Số tiền không hợp lệ. Vui lòng chỉ nhập số.\n\n"
                 "Hãy thử lại hoặc bấm nút Hủy bên dưới.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        await update.message.delete()
        return GET_AMOUNT

    order_id = context.user_data.get('refund_order_id')
    now = datetime.now()
    formatted_date = now.strftime("%d/%m/%Y %H:%M:%S")

    # Ghi dữ liệu vào Google Sheet bằng hàm từ utils.py
    try:
        append_to_sheet(SHEETS["REFUND"], [order_id, formatted_date, amount])
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

    # Chỉnh sửa tin nhắn của bot để báo thành công
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('refund_message_id'),
        text="✅ **THÀNH CÔNG!**\n\n"
             "Đã lưu thông tin hoàn tiền:\n"
             f"  - Mã Đơn Hàng: `{order_id}`\n"
             f"  - Số Tiền: `{amount_text}`\n"
             f"  - Thời Gian: `{formatted_date}`\n\n"
             "_Sẽ tự động quay về menu chính sau vài giây..._",
        parse_mode='Markdown'
    )
    
    # Dọn dẹp context
    context.user_data.clear()

    # Chờ 3 giây để người dùng đọc thông báo
    await asyncio.sleep(3)

    # Tự động quay về menu chính
    await show_outer_menu(update, context)
    
    return ConversationHandler.END

async def cancel_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy quy trình, dọn dẹp và quay về menu chính."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    logger.info("User cancelled the refund process.")
    
    await show_outer_menu(update, context)
    
    return ConversationHandler.END

def get_refund_conversation_handler() -> ConversationHandler:
    """Tạo và trả về ConversationHandler cho tính năng hoàn tiền."""
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