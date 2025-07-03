# refund.py

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Giả sử bạn có file g_sheets.py để tương tác với Google Sheet
# from g_sheets import append_to_sheet 
# from column import SHEETS

# Cấu hình logging
logger = logging.getLogger(__name__)

# Các trạng thái của cuộc hội thoại
GET_ORDER_ID, GET_AMOUNT = range(2)

async def start_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu cuộc hội thoại hoàn tiền, yêu cầu mã đơn hàng."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        text="💸 **QUY TRÌNH HOÀN TIỀN** 💸\n\n"
             "Vui lòng nhập **Mã Đơn Hàng** cần hoàn tiền.\n\n"
             "Nhập /huy để hủy bỏ.",
        parse_mode='Markdown'
    )
    return GET_ORDER_ID

async def handle_order_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lưu mã đơn hàng và yêu cầu số tiền."""
    order_id = update.message.text
    context.user_data['refund_order_id'] = order_id
    logger.info(f"Refund - Order ID: {order_id}")

    await update.message.reply_text(
        text=f"✅ Đã ghi nhận mã đơn: `{order_id}`\n\n"
             f"Bây giờ, vui lòng nhập **Số Tiền** cần hoàn.",
        parse_mode='Markdown'
    )
    return GET_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lưu số tiền, xử lý dữ liệu và kết thúc cuộc hội thoại."""
    amount_text = update.message.text
    try:
        # Cố gắng chuyển đổi thành số để xác thực
        amount = float(amount_text.replace(',', '').replace('.', ''))
    except ValueError:
        await update.message.reply_text(
            "Số tiền không hợp lệ. Vui lòng chỉ nhập số.\n"
            "Hãy thử lại hoặc nhập /huy để hủy bỏ."
        )
        return GET_AMOUNT # Yêu cầu nhập lại

    order_id = context.user_data.get('refund_order_id')
    logger.info(f"Refund - Amount: {amount} for Order ID: {order_id}")

    # Lấy ngày giờ hiện tại và định dạng
    now = datetime.now()
    formatted_date = now.strftime("%d/%m/%Y %H:%M:%S")

    # Chuẩn bị dữ liệu để ghi vào sheet
    row_data = [order_id, formatted_date, amount]

    try:
        # =================================================================
        # GỌI HÀM GHI VÀO GOOGLE SHEET TẠI ĐÂY
        # Ví dụ: append_to_sheet(SHEETS["REFUND"], row_data)
        # Vì chưa có hàm, chúng ta sẽ tạm log ra màn hình
        logger.info(f"Đang ghi vào sheet 'Hoàn Tiền': {row_data}")
        # =================================================================

        await update.message.reply_text(
            "✅ **THÀNH CÔNG!**\n\n"
            "Đã lưu thông tin hoàn tiền:\n"
            f"  - Mã Đơn Hàng: `{order_id}`\n"
            f"  - Số Tiền: `{amount_text}`\n"
            f"  - Thời Gian: `{formatted_date}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Lỗi khi ghi thông tin hoàn tiền: {e}")
        await update.message.reply_text(
            "❌ Đã xảy ra lỗi khi lưu thông tin. Vui lòng thử lại sau."
        )
        
    # Dọn dẹp context và kết thúc
    context.user_data.pop('refund_order_id', None)
    return ConversationHandler.END

async def cancel_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy bỏ quy trình hoàn tiền."""
    await update.message.reply_text("Đã hủy bỏ quy trình hoàn tiền.")
    context.user_data.pop('refund_order_id', None)
    # Có thể gọi lại menu chính ở đây nếu muốn
    # from menu import show_outer_menu
    # await show_outer_menu(update, context)
    return ConversationHandler.END

def get_refund_conversation_handler() -> ConversationHandler:
    """Tạo và trả về ConversationHandler cho tính năng hoàn tiền."""
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_refund, pattern="^start_refund$")],
        states={
            GET_ORDER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_id)],
            GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
        },
        fallbacks=[CommandHandler("huy", cancel_refund)],
        per_message=False
    )
    return conv_handler