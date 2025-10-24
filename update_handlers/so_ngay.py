import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler # Import ConversationHandler
from .common import (
    get_order_from_context,
    update_het_han,
    show_order_after_edit,
    handle_sheet_update_error
)
from utils import connect_to_sheet
from column import SHEETS, ORDER_COLUMNS
from update_order import EDIT_INPUT_SO_NGAY # Cần state này

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTION (MOVED FROM update_order.py) ---

async def input_new_so_ngay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật SỐ NGÀY (tự động cập nhật HẾT HẠN)."""
    new_so_ngay_str = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx') # Should be ORDER_COLUMNS['SO_NGAY']
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        return ConversationHandler.END # End if order not found

    # Validate input (must be a positive integer)
    if not new_so_ngay_str.isdigit() or int(new_so_ngay_str) <= 0:
        # Inform user and ask again
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text="⚠️ Số ngày không hợp lệ (cần là một số > 0). Vui lòng nhập lại:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
        )
        # Return to the same state to wait for new input
        return EDIT_INPUT_SO_NGAY

    # Convert to integer for saving
    new_so_ngay_num = int(new_so_ngay_str)

    # Update sheet
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])

        # 1. Update SỐ NGÀY in sheet (save number) and cache (save string)
        sheet.update_cell(row_idx, col_idx + 1, new_so_ngay_num) # Save number
        original_row_data[col_idx] = new_so_ngay_str # Save string in cache for display

        # 2. Trigger HẾT HẠN update (using old NGAY_DK, new SO_NGAY)
        # update_het_han will read the string 'new_so_ngay_str' from cache
        await update_het_han(original_row_data, row_idx, sheet)

    except Exception as e:
        # Use common error handler
        return await handle_sheet_update_error(update, context, e, "cập nhật Số Ngày và Hết Hạn")

    # Show updated order details
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật SỐ NGÀY & HẾT HẠN thành công!")