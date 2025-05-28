from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from utils import connect_to_sheet
from menu import show_outer_menu
from config import logger

ASK_MA_DON, XAC_NHAN_XOA = range(2)

# Bắt đầu xóa đơn
async def start_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🗑️ Vui lòng nhập *Mã đơn hàng* bạn muốn xóa:", parse_mode="Markdown")
    return ASK_MA_DON

# Nhận mã đơn và xác nhận xóa
async def nhan_ma_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ma_don = update.message.text.strip()
    sheet = connect_to_sheet()

    try:
        ma_don_list = sheet.col_values(1)  # Duyệt cột A (mã đơn)
        for i, ma in enumerate(ma_don_list):
            if ma == ma_don:
                row_index = i + 1
                row_data = sheet.row_values(row_index)

                context.user_data["row_index"] = row_index
                context.user_data["ma_don"] = ma_don

                ten_sp = row_data[0] if len(row_data) > 0 else ""
                thong_tin = row_data[1] if len(row_data) > 1 else ""
                khach = row_data[2] if len(row_data) > 2 else ""

                msg = (
                    f"⚠️ Xác nhận xóa đơn:\n"
                    f"📦 Mã đơn: `{ma_don}`\n"
                    f"🔹 Tên sản phẩm: {ten_sp}\n"
                    f"🔹 Thông tin: {thong_tin}\n"
                    f"👤 Khách hàng: {khach}"
                )
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Xác nhận xóa", callback_data="confirm_delete"),
                        InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
                return XAC_NHAN_XOA

        # Nếu không tìm thấy
        await update.message.reply_text("❌ Không tìm thấy đơn hàng với mã bạn đã nhập.")
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Lỗi khi tra mã đơn: {e}")
        await update.message.reply_text("⚠️ Đã xảy ra lỗi khi truy cập Google Sheet.")
        return ConversationHandler.END


# Thực hiện xóa đơn
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    row_index = context.user_data.get("row_index")
    sheet = connect_to_sheet()
    sheet.delete_rows(row_index)
    await query.edit_message_text("✅ Đơn hàng đã được *xóa thành công*.", parse_mode="Markdown")
    return ConversationHandler.END

# Hủy thao tác
async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_outer_menu(update, context)
    return ConversationHandler.END

# Trả về ConversationHandler chính
def get_delete_order_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_delete_order, pattern="^delete_order$")],
        states={
            ASK_MA_DON: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhan_ma_don)],
            XAC_NHAN_XOA: [
                CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$"),
                CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$")
            ]
        },
        fallbacks=[],
    )

# Trả về các callback phụ trợ khác
def get_delete_callbacks():
    return [
        CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$"),
        CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$")
    ]
