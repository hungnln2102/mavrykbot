import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from .common import get_order_from_context, show_order_after_edit, handle_sheet_update_error
from utils import connect_to_sheet, chuan_hoa_gia, escape_mdv2
from column import SHEETS, ORDER_COLUMNS
from update_order import EDIT_INPUT_SIMPLE

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTION (MOVED FROM update_order.py) ---

async def input_new_simple_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật cho các trường đơn giản."""
    new_value_raw = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx')
    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        # Sử dụng helper show_order_after_edit để hiển thị lỗi và quay lại
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        # Cần import END từ ConversationHandler hoặc trả về giá trị số tương ứng
        from telegram.ext import ConversationHandler
        return ConversationHandler.END # Kết thúc nếu không tìm thấy đơn

    value_to_save = new_value_raw
    value_to_cache = new_value_raw

    # Xử lý đặc biệt cho các cột giá
    if col_idx in [ORDER_COLUMNS['GIA_BAN'], ORDER_COLUMNS['GIA_NHAP']]:
        gia_text, gia_num = chuan_hoa_gia(new_value_raw)
        if not gia_text or gia_text == "0":
            # Thông báo lỗi và yêu cầu nhập lại
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data.get('main_message_id'),
                text="⚠️ Giá không hợp lệ. Vui lòng nhập lại:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
            )
            # Quay lại chính state này để chờ nhập lại
            return EDIT_INPUT_SIMPLE

        value_to_save = gia_num  # Ghi SỐ vào sheet
        value_to_cache = gia_text # Ghi CHUỖI vào cache

    # Xử lý cập nhật sheet
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        # Cập nhật ô trong Google Sheet
        sheet.update_cell(row_idx, col_idx + 1, value_to_save)
        # Cập nhật cache (dữ liệu trong bộ nhớ của bot)
        original_row_data[col_idx] = value_to_cache
    except Exception as e:
        # Sử dụng helper xử lý lỗi chung
        return await handle_sheet_update_error(update, context, e, f"cập nhật ô cột {col_idx}")

    # Hiển thị lại đơn hàng với thông báo thành công
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật thành công!")