# update_handlers/nguon.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

# --- IMPORT HELPERS ---
from .common import (
    get_order_from_context,
    update_gia_nhap,
    show_order_after_edit,
    handle_sheet_update_error
)
from ..utils import connect_to_sheet
from ..column import SHEETS, ORDER_COLUMNS

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTION (MOVED FROM update_order.py) ---

async def input_new_nguon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật NGUỒN (tự động cập nhật GIÁ NHẬP)."""
    new_nguon = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx') # Should be ORDER_COLUMNS['NGUON']
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        from telegram.ext import ConversationHandler
        return ConversationHandler.END # End if order not found

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])

        # 1. Cập nhật NGUỒN vào sheet và cache
        sheet.update_cell(row_idx, col_idx + 1, new_nguon)
        original_row_data[col_idx] = new_nguon # Update cache

        # 2. Kích hoạt cập nhật GIÁ NHẬP (dùng SP cũ, Nguồn mới)
        await update_gia_nhap(original_row_data, row_idx, sheet)

    except Exception as e:
        # Sử dụng helper xử lý lỗi chung
        return await handle_sheet_update_error(update, context, e, "cập nhật Nguồn và Giá Nhập")

    # Hiển thị lại đơn hàng với thông báo thành công
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật NGUỒN & GIÁ NHẬP thành công!")