# update_handlers/ngay_dk.py
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler # Import ConversationHandler

# --- IMPORT HELPERS ---
from .common import (
    get_order_from_context,
    update_het_han,
    show_order_after_edit,
    handle_sheet_update_error
)
from utils import connect_to_sheet, escape_mdv2
from column import SHEETS, ORDER_COLUMNS

# --- IMPORT STATES (để return về state cũ nếu validate lỗi) ---
from update_states import EDIT_INPUT_NGAY_DK # Cần state này

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTION (MOVED FROM update_order.py) ---

async def input_new_ngay_dk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật NGÀY ĐĂNG KÝ (tự động cập nhật HẾT HẠN)."""
    new_ngay_dk = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx') # Should be ORDER_COLUMNS['NGAY_DANG_KY']
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        return ConversationHandler.END # End if order not found

    # Validate date format
    try:
        datetime.strptime(new_ngay_dk, "%d/%m/%Y")
    except ValueError:
        # Inform user and ask again
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text="⚠️ Định dạng ngày không hợp lệ (cần `dd/mm/yyyy`). Vui lòng nhập lại:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
        )
        # Return to the same state to wait for new input
        return EDIT_INPUT_NGAY_DK

    # Update sheet
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])

        # 1. Update NGÀY ĐĂNG KÝ in sheet and cache
        sheet.update_cell(row_idx, col_idx + 1, new_ngay_dk)
        original_row_data[col_idx] = new_ngay_dk # Update cache

        # 2. Trigger HẾT HẠN update (using new NGAY_DK, old SO_NGAY)
        await update_het_han(original_row_data, row_idx, sheet)

    except Exception as e:
        # Use common error handler
        return await handle_sheet_update_error(update, context, e, "cập nhật Ngày ĐK và Hết Hạn")

    # Show updated order details
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật NGÀY ĐK & HẾT HẠN thành công!")