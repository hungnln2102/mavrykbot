
# delete_order.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ConversationHandler, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from utils import connect_to_sheet
from menu import show_main_selector

ASK_ORDER_ID = 1

def escape_markdown(text: str) -> str:
    import re
    return re.sub(r'([_*\[\]()~`>#+=|{}.!\\-])', r'\\\1', text)

# Bắt đầu xóa đơn hàng
async def start_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("🔍 Vui lòng nhập mã đơn hàng bạn muốn xóa:")
    else:
        await update.message.reply_text("🔍 Vui lòng nhập mã đơn hàng bạn muốn xóa:")
    return ASK_ORDER_ID

# Xử lý mã đơn và xác nhận
async def ask_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ma_don = update.message.text.strip()
    context.user_data['ma_don_can_xoa'] = ma_don

    sheet = connect_to_sheet()
    data = sheet.get_all_values()

    for idx, row in enumerate(data):
        if row and row[0].strip() == ma_don:
            context.user_data['row_to_delete'] = idx + 1
            ten_sp = escape_markdown(row[1])
            ten_kh = escape_markdown(row[2])
            ma_don = escape_markdown(ma_don)
            await update.message.reply_text(
                f"❗Bạn có chắc muốn xóa đơn hàng sau không?"
                f"🆔 Mã đơn: `{ma_don}`"
                f"🛍️ Sản phẩm: {ten_sp}"
                f"👤 Khách hàng: {ten_kh}",
                parse_mode='MarkdownV2',
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Đồng ý xóa", callback_data="confirm_delete"),
                        InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")
                    ]
                ])
            )
            return ConversationHandler.END

    await update.message.reply_text("❌ Không tìm thấy đơn hàng với mã đã nhập.Vui lòng nhập lại:")
    return ASK_ORDER_ID

# Thực hiện xóa đơn hàng
async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    row_index = context.user_data.get('row_to_delete')
    if row_index:
        sheet = connect_to_sheet()
        sheet.delete_rows(row_index)
        await query.edit_message_text("🗑️ Đơn hàng đã được xóa thành công!")
    else:
        await query.edit_message_text("⚠️ Không thể xác định đơn hàng cần xóa.")

    await show_main_selector(update, context, edit=True)

# Hủy xóa
async def cancel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("❎ Đã hủy thao tác xóa đơn hàng.")
    await show_main_selector(update, context, edit=True)

# Tạo conversation handler
def get_delete_order_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("delete", start_delete_order),
            CallbackQueryHandler(start_delete_order, pattern="^delete$")
        ],
        states={
            ASK_ORDER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_delete_confirm)]
        },
        fallbacks=[],
        name="delete_order_conversation",
        persistent=False
    )

# Callback xác nhận xoá
def get_delete_callbacks():
    return [
        CallbackQueryHandler(confirm_delete_callback, pattern="^confirm_delete$"),
        CallbackQueryHandler(cancel_delete_callback, pattern="^cancel_delete$")
    ]
