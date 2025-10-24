import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler # Import ConversationHandler
from .common import (
    get_order_from_context,
    show_order_after_edit,
    handle_sheet_update_error
)
from utils import connect_to_sheet
from column import SHEETS, ORDER_COLUMNS
from update_order import EDIT_INPUT_LINK_KHACH # Cần state này

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTIONS (MOVED FROM update_order.py) ---

async def input_new_ten_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật TÊN KHÁCH (Bước 1/2: Cập nhật tên, hỏi link)."""
    new_ten_khach = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx') # Should be ORDER_COLUMNS['TEN_KHACH']
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        return ConversationHandler.END # End if order not found

    # Update sheet immediately
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        # 1. Update TÊN KHÁCH in sheet and cache
        sheet.update_cell(row_idx, col_idx + 1, new_ten_khach)
        original_row_data[col_idx] = new_ten_khach # Update cache
    except Exception as e:
        # Use common error handler
        return await handle_sheet_update_error(update, context, e, "cập nhật Tên Khách")

    # 2. Ask for LINK KHÁCH
    keyboard = [
        [InlineKeyboardButton("Bỏ qua", callback_data="skip_link_khach")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]
    ]
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text=f"✅ Đã cập nhật Tên Khách.\n\n🔗 Vui lòng nhập *Link Khách* (hoặc Bỏ qua):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Move to the state waiting for the link input
    return EDIT_INPUT_LINK_KHACH

async def input_new_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật LINK KHÁCH (Bước 2/2: Cập nhật link)."""
    new_link_khach = update.message.text.strip()
    await update.message.delete()

    # We know the column index must be LINK_KHACH here
    col_idx = ORDER_COLUMNS['LINK_KHACH']
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    # Check again if order data exists (unlikely to fail here, but good practice)
    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để cập nhật Link Khách."
        )
        return ConversationHandler.END # End if order not found

    # Update sheet
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        # Update LINK KHÁCH in sheet and cache
        sheet.update_cell(row_idx, col_idx + 1, new_link_khach)
        original_row_data[col_idx] = new_link_khach # Update cache
    except Exception as e:
        # Use common error handler
        return await handle_sheet_update_error(update, context, e, "cập nhật Link Khách")

    # Show updated order details (both name and link)
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật Tên Khách & Link Khách thành công!")

async def skip_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng chọn Bỏ qua LINK KHÁCH (Bước 2/2)."""
    query = update.callback_query
    await query.answer("Đã bỏ qua Link Khách")

    # Customer Name was already updated in the previous step.
    # Just show the order details again.
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật Tên Khách thành công (bỏ qua link).")