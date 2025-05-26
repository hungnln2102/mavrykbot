# update_order.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_menu

logger = logging.getLogger(__name__)

SELECT_MODE, INPUT_VALUE, SELECT_FIELD, INPUT_NEW_VALUE = range(4)

async def start_update_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Kiểm tra theo Mã Đơn Hàng", callback_data="check_ma_don")],
        [InlineKeyboardButton("❌ Kết Thúc", callback_data="cancel_update")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📋 Vui lòng chọn hình thức kiểm tra:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("📋 Vui lòng chọn hình thức kiểm tra:", reply_markup=reply_markup)
    return SELECT_MODE

async def select_check_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['check_mode'] = query.data

    if query.data == "check_ma_don":
        keyboard = [
            [InlineKeyboardButton("❌ Kết Thúc", callback_data="cancel_update")]
        ]
        await query.message.reply_text("🔢 Vui lòng nhập mã đơn hàng:", reply_markup=InlineKeyboardMarkup(keyboard))
        return INPUT_VALUE

    return await cancel_update(update, context)

async def input_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    sheet = connect_to_sheet()
    data = sheet.get_all_values()

    for idx, row in enumerate(data):
        if row and row[0] == text:
            context.user_data['selected_row'] = idx + 1
            context.user_data['ma_don'] = row[0]

            slot = f"🎯 Slot: {row[4]}\n" if row[4] else ""
            message = (
                f"🔍 Thông tin đơn hàng với Mã Đơn Hàng: {row[0]}\n\n"
                f"🏍️ Sản phẩm: {row[1]}\n"
                f"📄 Thông tin sản phẩm: {row[2]}\n"
                f"👤 Khách Hàng: {row[3]}\n"
                f"{slot}"
                f"📅 Ngày đăng ký: {row[5]}\n"
                f"📆 Số ngày đã đăng ký: {row[6]}\n"
                f"⏳ Ngày hết hạn: {row[7]}\n"
                f"📉 Số ngày còn lại: {row[8]}\n"
                f"🚚 Nguồn cấp hàng: {row[9]}\n"
                f"🧾 Giá nhập: {row[10]}\n"
                f"💵 Giá bán: {row[11]}"
            )
            buttons = [
                [
                    InlineKeyboardButton("🛠 Cập nhật đơn", callback_data="start_edit"),
                    InlineKeyboardButton("❌ Kết Thúc", callback_data="cancel_update")
                ]
            ]
            await update.message.reply_text(
                escape_markdown(message, version=2),
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return SELECT_FIELD

    await update.message.reply_text("❌ Không tìm thấy mã đơn hàng. Quay về menu chính.")
    return await cancel_update(update, context)

async def start_edit_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📆 Số Ngày Đã Đăng Ký", callback_data="edit_col_6")],
        [InlineKeyboardButton("💵 Giá Bán", callback_data="edit_col_11")],
        [InlineKeyboardButton("🚚 Nguồn Cấp Hàng", callback_data="edit_col_9")],
        [InlineKeyboardButton("🧾 Giá Nhập", callback_data="edit_col_10")],
        [InlineKeyboardButton("❌ Kết Thúc", callback_data="cancel_update")]
    ]
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "📋 Vui lòng chọn nội dung cần chỉnh sửa:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_FIELD

async def choose_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_column'] = query.data.split("_")[-1]
    await query.message.reply_text("✏️ Vui lòng nhập nội dung cần chỉnh sửa:")
    return INPUT_NEW_VALUE

async def input_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    sheet = connect_to_sheet()
    row_idx = context.user_data.get("selected_row")
    col_idx = context.user_data.get("edit_column")

    if not row_idx or not col_idx:
        await update.message.reply_text("⚠️ Không xác định được dòng cần cập nhật.")
        return await cancel_update(update, context)

    try:
        sheet.update_cell(row_idx, int(col_idx) + 1, text)
        updated = sheet.row_values(row_idx)

        await update.message.reply_text(
            f"✅ Đơn hàng với mã đơn hàng `{updated[0]}` đã được chỉnh sửa thành công.\n\n"
            f"📉 *Số ngày còn lại*: `{updated[8]}`\n"
            f"⏳ *Ngày hết hạn*: `{updated[7]}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Cập nhật thất bại: {str(e)}")

    return await cancel_update(update, context)

async def cancel_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await show_menu(update, context)
    return ConversationHandler.END

def get_update_order_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("update", start_update_order),
            CallbackQueryHandler(start_update_order, pattern="^update$")
        ],
        states={
            SELECT_MODE: [CallbackQueryHandler(select_check_mode, pattern="^check_ma_don$")],
            INPUT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_value_handler)],
            SELECT_FIELD: [
                CallbackQueryHandler(start_edit_update, pattern="^start_edit$"),
                CallbackQueryHandler(choose_field_to_edit, pattern="^edit_col_.*")
            ],
            INPUT_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_value_handler)]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_update, pattern="^cancel_update$"),
            CommandHandler("cancel", cancel_update)
        ],
        name="update_order_conversation",
        persistent=False
    )
