from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_main_selector

# Trạng thái hội thoại
ASK_ORDER_ID, CONFIRM_DELETE = range(2)

# Bắt đầu quy trình xóa đơn
async def start_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "📌 Vui lòng nhập *Mã Đơn Hàng* bạn muốn xóa:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message, parse_mode="MarkdownV2")
    elif update.message:
        await update.message.reply_text(message, parse_mode="MarkdownV2")
    return ASK_ORDER_ID

# Nhập mã đơn hàng → kiểm tra trong sheet
async def handle_order_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ma_don_raw = update.message.text.strip()
    sheet = connect_to_sheet()
    all_data = sheet.get_all_values()

    for index, row in enumerate(all_data[1:], start=2):  # Bỏ dòng tiêu đề
        if row[0] == ma_don_raw:
            # Lưu thông tin để dùng khi xác nhận xóa
            context.user_data["row_to_delete"] = index
            context.user_data["ma_don"] = ma_don_raw

            # Escape dữ liệu
            ma_don = escape_markdown(ma_don_raw, version=2)
            ten_san_pham = escape_markdown(row[0], version=2)
            thong_tin_don = escape_markdown(row[1], version=2)
            khach_hang = escape_markdown(row[2], version=2)

            # Hiển thị xác nhận
            text = (
                f"⚠️ *Xác nhận xóa đơn hàng:*\n"
                f"📦 Mã đơn: `{ma_don}`\n"
                f"🔹 Sản phẩm: {ten_san_pham}\n"
                f"🔹 Thông tin đơn: {thong_tin_don}\n"
                f"🔹 Khách hàng: {khach_hang}"
            )
            buttons = [
                [InlineKeyboardButton("✅ Xác nhận xóa", callback_data="confirm_delete")],
                [InlineKeyboardButton("🔙 Quay lại", callback_data="cancel_delete")]
            ]
            await update.message.reply_text(text, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(buttons))
            return CONFIRM_DELETE

    # Không tìm thấy
    await update.message.reply_text("❌ Không tìm thấy đơn hàng với mã đã nhập.")
    return ConversationHandler.END

# Xác nhận xóa → xóa dòng khỏi Sheet
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    row = context.user_data.get("row_to_delete")
    sheet = connect_to_sheet()
    sheet.delete_row(row)

    ma_don = escape_markdown(context.user_data["ma_don"], version=2)
    await query.edit_message_text(
        f"✅ Đã xóa đơn hàng `{ma_don}` thành công.",
        parse_mode="MarkdownV2"
    )
    return await show_main_selector(update, context)

# Quay lại menu
async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await show_main_selector(update, context)

# Đăng ký hội thoại /delete
def get_delete_order_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("delete", start_delete_order)],
        states={
            ASK_ORDER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_id)],
            CONFIRM_DELETE: [
                CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$"),
                CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$")
            ]
        },
        fallbacks=[],
    )

# Callback cho nút "🗑️ Xóa Đơn" từ menu
def get_delete_callbacks():
    return [
        CallbackQueryHandler(start_delete_order, pattern="^delete$")
    ]
