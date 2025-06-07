from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
import asyncio

from utils import connect_to_sheet
from config import logger
from menu import show_main_selector

ASK_MA_DON = range(1)

# 👉 Bắt đầu xóa đơn
async def start_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_msg = await query.edit_message_text(
        "🗑️ Vui lòng nhập *Mã đơn hàng* bạn muốn kiểm tra:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    context.user_data["ma_don_input_msg_id"] = sent_msg.message_id
    return ASK_MA_DON

# 👉 Hiển thị thông tin đơn hàng
def format_order_info(ma_don, row):
    def safe(i): return escape_markdown(row[i], version=2) if len(row) > i and row[i].strip() else ""
    return (
        f"🧾 *Xác nhận xóa đơn hàng:*\n"
        f"📦 *Mã đơn:* `{escape_markdown(ma_don, version=2)}`\n"
        f"🔹 *Sản phẩm:* {safe(1)}\n"
        f"📝 *Thông tin sản phẩm:* {safe(2)}\n"
        f"👤 *Khách:* {safe(3)}\n"
        + (f"📌 *Slot:* {safe(4)}\n" if safe(4) else "")
        + f"📅 *Ngày đăng ký:* {safe(5)}\n"
        + f"📆 *Số ngày:* {safe(6)} ngày\n"
        + f"💰 *Giá:* {safe(10)}"
    )

# 👉 Nhận mã đơn và hiển thị thông tin
async def nhan_ma_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ma_don = update.message.text.strip()
    context.user_data["ma_don_can_xoa"] = ma_don

    # ❌ Xoá nút "Hủy" ở bước nhập
    try:
        msg_id = context.user_data.get("ma_don_input_msg_id")
        if msg_id:
            await context.bot.edit_message_reply_markup(
                chat_id=update.message.chat_id,
                message_id=msg_id,
                reply_markup=None
            )
    except Exception as e:
        logger.warning(f"[⚠️ Không thể xoá nút nhập mã]: {e}")

    logger.info(f"🔍 Nhận mã đơn từ người dùng: {ma_don}")

    try:
        sheet = connect_to_sheet().worksheet("Test")
        data = sheet.get_all_values()

        for i, row in enumerate(data):
            if row and row[0] == ma_don:
                context.user_data["row_index"] = i + 1
                keyboard = [[
                    InlineKeyboardButton("✅ Xác Nhận Xóa", callback_data=f"confirm_delete_{ma_don}"),
                    InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    text=format_order_info(ma_don, row),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=reply_markup
                )
                return ConversationHandler.END

        # Không tìm thấy
        keyboard = [
            [InlineKeyboardButton("🔁 Nhập lại mã đơn", callback_data="retry_delete")],
            [InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")]
        ]
        await update.message.reply_text(
            "❌ Không tìm thấy đơn hàng với mã bạn đã nhập.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"⚠️ Lỗi khi truy cập Sheet: {e}")
        await update.message.reply_text("⚠️ Đã xảy ra lỗi khi truy cập dữ liệu.")
        return ConversationHandler.END

# 👉 Xác nhận xóa đơn
async def confirm_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("_")[-1]
    row_index = context.user_data.get("row_index")

    if not row_index:
        await query.edit_message_text("⚠️ Không tìm thấy thông tin dòng cần xóa.")
        return

    try:
        sheet = connect_to_sheet().worksheet("Test")
        sheet.delete_rows(row_index)

        # 🧹 Gỡ nút cũ và thay nội dung bằng thông báo xóa thành công
        await query.message.edit_text(
            text=f"✅ Đơn hàng `{escape_markdown(ma_don, version=2)}` đã được *xóa thành công*\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )

        # 🆕 Gửi menu mới (không sửa lại dòng trên)
        await show_main_selector(update, context, edit=False)

    except Exception as e:
        logger.error(f"Lỗi khi xóa đơn: {e}")
        await query.edit_message_text("⚠️ Đã xảy ra lỗi khi xóa đơn hàng.")

# 👉 Hủy thao tác xóa
async def cancel_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.warning(f"[⚠️ Không thể xoá nút hủy]: {e}")

    context.user_data.clear()
    await query.message.edit_text("❌ Đã hủy thao tác xóa đơn hàng.")
    await show_main_selector(update, context, edit=False)
    return ConversationHandler.END

# 👉 Conversation handler
def get_delete_order_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_delete_order, pattern="^delete_order$"),
            CallbackQueryHandler(start_delete_order, pattern="^retry_delete$")
        ],
        states={
            ASK_MA_DON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nhan_ma_don),
                CallbackQueryHandler(cancel_delete_order, pattern="^cancel_delete$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_delete_order, pattern="^cancel_delete$")
        ]
    )

# 👉 Callback handler riêng
def get_delete_callbacks():
    return [
        CallbackQueryHandler(confirm_delete_order, pattern=r"^confirm_delete_"),
        CallbackQueryHandler(cancel_delete_order, pattern="^cancel_delete$"),
        CallbackQueryHandler(start_delete_order, pattern="^retry_delete$")
    ]
