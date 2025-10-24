# update_handlers/san_pham.py
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

# --- IMPORT HELPERS ---
from .common import (
    get_order_from_context,
    update_gia_nhap,
    update_het_han,
    show_order_after_edit,
    handle_sheet_update_error
)
from utils import connect_to_sheet, escape_mdv2
# Import normalize_product_duration trực tiếp từ update_order.py nếu cần
# Hoặc chuyển nó vào utils.py nếu nhiều nơi dùng
from update_order import normalize_product_duration
from column import SHEETS, ORDER_COLUMNS

# --- IMPORT STATES (để return về state cũ nếu validate lỗi) ---
from update_states import EDIT_INPUT_SAN_PHAM # Cần state này

logger = logging.getLogger(__name__)

# --- HANDLER FUNCTION (MOVED FROM update_order.py) ---

async def input_new_san_pham_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý cập nhật SẢN PHẨM (tự động cập nhật SỐ NGÀY, GIÁ NHẬP, HẾT HẠN)."""
    new_value_raw = update.message.text.strip()
    await update.message.delete()

    ma_don, row_idx, original_row_data = get_order_from_context(context)

    if not original_row_data:
        await show_order_after_edit(
            update,
            context,
            success_notice="❌ Lỗi: Không tìm thấy đơn hàng trong cache để sửa."
        )
        from telegram.ext import ConversationHandler
        return ConversationHandler.END # Kết thúc nếu không tìm thấy đơn

    # 1. Chuẩn hóa tên sản phẩm
    new_san_pham = normalize_product_duration(new_value_raw)

    # 2. Phân tích tên SP để lấy SỐ NGÀY
    match_thoi_han = re.search(r"--\s*(\d+)\s*m", new_san_pham, flags=re.I)

    if not match_thoi_han:
        # Nếu không tìm thấy thời hạn, báo lỗi và yêu cầu nhập lại
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=f"⚠️ Tên sản phẩm *{escape_mdv2(new_san_pham)}* không hợp lệ.\n"
                 f"Cần có thời hạn (ví dụ: `--12m`). Vui lòng nhập lại:",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
        )
        # Quay lại chính state này để chờ nhập lại
        return EDIT_INPUT_SAN_PHAM

    # 3. Tính toán số ngày
    so_thang = int(match_thoi_han.group(1))
    new_so_ngay = 365 if so_thang == 12 else (so_thang * 30)

    # 4. Thực hiện cập nhật sheet
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])

        # 4.1 Cập nhật SẢN PHẨM
        col_san_pham = ORDER_COLUMNS['SAN_PHAM']
        sheet.update_cell(row_idx, col_san_pham + 1, new_san_pham)
        original_row_data[col_san_pham] = new_san_pham # Cập nhật cache

        # 4.2 Cập nhật SỐ NGÀY
        col_so_ngay = ORDER_COLUMNS['SO_NGAY']
        sheet.update_cell(row_idx, col_so_ngay + 1, new_so_ngay) # Ghi SỐ vào sheet
        original_row_data[col_so_ngay] = str(new_so_ngay) # Lưu CHUỖI vào cache

        # 4.3 Cập nhật GIÁ NHẬP (dùng SP mới, Nguồn cũ) - Hàm này tự ghi vào sheet và cache
        await update_gia_nhap(original_row_data, row_idx, sheet)

        # 4.4 Cập nhật HẾT HẠN (dùng Ngày ĐK cũ, Số Ngày mới) - Hàm này tự ghi vào sheet và cache
        await update_het_han(original_row_data, row_idx, sheet)

    except Exception as e:
        # Sử dụng helper xử lý lỗi chung
        return await handle_sheet_update_error(update, context, e, "cập nhật Sản Phẩm và các trường liên quan")

    # Hiển thị lại đơn hàng với thông báo thành công
    return await show_order_after_edit(update, context, success_notice="✅ Cập nhật SẢN PHẨM, SỐ NGÀY, GIÁ NHẬP & HẾT HẠN thành công!")