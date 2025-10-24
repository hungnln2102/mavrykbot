# update_handlers/common.py
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import gspread
from utils import connect_to_sheet, chuan_hoa_gia, escape_mdv2
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX
from add_order import tinh_ngay_het_han
from update_order import show_matched_order, end_update

logger = logging.getLogger(__name__)

def get_order_from_context(context: ContextTypes.DEFAULT_TYPE):
    ma_don = context.user_data.get('edit_ma_don')
    matched_orders = context.user_data.get('matched_orders', [])

    if not ma_don:
        return None, -1, None

    for order_info in matched_orders:
        try:
            if str(order_info['data'][ORDER_COLUMNS["ID_DON_HANG"]]).strip() == str(ma_don).strip():
                return ma_don, order_info['row_index'], order_info['data']
        except (IndexError, KeyError):
            continue

    return ma_don, -1, None

async def update_gia_nhap(
    sheet_row_data: list,
    sheet_row_idx: int,
    ws: gspread.Worksheet
) -> tuple[str, int]:
    try:
        san_pham = str(sheet_row_data[ORDER_COLUMNS["SAN_PHAM"]]).strip()
        nguon_hang = str(sheet_row_data[ORDER_COLUMNS["NGUON"]]).strip()
        gia_nhap_cu = str(sheet_row_data[ORDER_COLUMNS["GIA_NHAP"]]).strip()
    except IndexError:
        logger.warning(f"Thiếu dữ liệu trong sheet_row_data (hàng {sheet_row_idx}) để cập nhật giá nhập.")
        return "0", 0

    gia_nhap_moi = None
    try:
        sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
        ty_gia_data = sheet_ty_gia.get_all_values(value_render_option='FORMATTED_VALUE')

        headers = ty_gia_data[0] if ty_gia_data else []

        nguon_col_idx = -1
        for i, header_name in enumerate(headers):
            if str(header_name).strip().lower() == nguon_hang.strip().lower():
                nguon_col_idx = i
                break

        product_row = None
        for row in ty_gia_data[1:]:
            if len(row) > TYGIA_IDX["SAN_PHAM"]:
                ten_sp_tygia = str(row[TYGIA_IDX["SAN_PHAM"]])
                if ten_sp_tygia.strip().lower() == san_pham.strip().lower():
                    product_row = row
                    break
            else:
                 logger.debug(f"Hàng trong sheet Tỷ Giá không đủ cột: {row}")


        if product_row and nguon_col_idx != -1 and len(product_row) > nguon_col_idx:
            gia_nhap_raw = str(product_row[nguon_col_idx])
            _, gia_nhap_moi = chuan_hoa_gia(gia_nhap_raw)
        elif product_row and nguon_col_idx == -1:
             logger.warning(f"Không tìm thấy cột nguồn '{nguon_hang}' trong sheet Tỷ Giá.")
        elif not product_row:
             logger.warning(f"Không tìm thấy sản phẩm '{san_pham}' trong sheet Tỷ Giá.")


    except gspread.exceptions.WorksheetNotFound:
         logger.error(f"Không tìm thấy sheet '{SHEETS['EXCHANGE']}'.")
    except Exception as e:
        logger.warning(f"Lỗi khi truy cập '{SHEETS['EXCHANGE']}': {e}")

    final_gia_nhap_num = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
    final_gia_nhap_str = "{:,}".format(final_gia_nhap_num or 0)

    try:
        # Ghi SỐ (number) vào Sheet
        ws.update_cell(sheet_row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, final_gia_nhap_num)
        # Lưu CHUỖI (string) vào cache để hiển thị
        sheet_row_data[ORDER_COLUMNS["GIA_NHAP"]] = final_gia_nhap_str
    except Exception as update_err:
         logger.error(f"Lỗi khi cập nhật giá nhập vào sheet tại hàng {sheet_row_idx}: {update_err}")
         # Nếu cập nhật sheet lỗi, trả về giá trị cũ để cache không bị sai
         return gia_nhap_cu, chuan_hoa_gia(gia_nhap_cu)[1]


    return final_gia_nhap_str, final_gia_nhap_num

async def update_het_han(
    sheet_row_data: list,
    sheet_row_idx: int,
    ws: gspread.Worksheet # Sử dụng type hint rõ ràng
) -> str: # Type hint cho giá trị trả về
    """
    Tự động cập nhật HET_HAN và CON_LAI dựa trên NGAY_DANG_KY và SO_NGAY.
    Cập nhật cả sheet và cache.
    Trả về ngày hết hạn mới (str).
    """
    try:
        ngay_dk_str = str(sheet_row_data[ORDER_COLUMNS["NGAY_DANG_KY"]]).strip()
        so_ngay_str = str(sheet_row_data[ORDER_COLUMNS["SO_NGAY"]]).strip()
        try:
            from ..utils import VN_TZ
        except ImportError:
            VN_TZ = timezone(timedelta(hours=7))

    except IndexError:
        logger.warning(f"Thiếu dữ liệu trong sheet_row_data (hàng {sheet_row_idx}) để cập nhật ngày hết hạn.")
        return "" # Trả về chuỗi rỗng nếu lỗi

    het_han_cu_str = ""
    try:
        het_han_cu_str = str(sheet_row_data[ORDER_COLUMNS["HET_HAN"]]).strip()
    except (IndexError, KeyError):
        pass # Không sao nếu chưa có

    if not ngay_dk_str or not so_ngay_str or not so_ngay_str.isdigit():
        logger.warning(f"Ngày ĐK ({ngay_dk_str}) hoặc Số Ngày ({so_ngay_str}) không hợp lệ tại hàng {sheet_row_idx}.")
        return het_han_cu_str # Trả về giá trị cũ

    try:
        ngay_dk_dt = datetime.strptime(ngay_dk_str, "%d/%m/%Y")
        so_ngay_int = int(so_ngay_str)
        ngay_het_han_dt = ngay_dk_dt + timedelta(days=so_ngay_int) # Hoặc days=so_ngay_int - 1 tùy logic
        ngay_het_han_moi_str = ngay_het_han_dt.strftime("%d/%m/%Y")

        today_vn = datetime.now(VN_TZ).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        delta_days = (ngay_het_han_dt.replace(tzinfo=None) - today_vn).days
        con_lai_moi_int = max(0, delta_days + 1)

    except (ValueError, TypeError) as e:
        logger.warning(f"Không thể tính ngày hết hạn/còn lại từ {ngay_dk_str} và {so_ngay_str} (hàng {sheet_row_idx}): {e}")
        return het_han_cu_str # Trả về giá trị cũ

    try:
        ws.update_cell(sheet_row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi_str)
        sheet_row_data[ORDER_COLUMNS["HET_HAN"]] = ngay_het_han_moi_str # Cập nhật cache Hết Hạn

        try:
            sheet_row_data[ORDER_COLUMNS["CON_LAI"]] = str(con_lai_moi_int) # Lưu chuỗi vào cache
        except (IndexError, KeyError):
            logger.debug(f"Không tìm thấy cột CON_LAI để cập nhật cache tại hàng {sheet_row_idx}.")
            pass

    except Exception as sheet_error:
        logger.error(f"Lỗi khi cập nhật sheet (Hết Hạn/Còn Lại) tại hàng {sheet_row_idx}: {sheet_error}")
        return het_han_cu_str

    return ngay_het_han_moi_str

async def show_order_after_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, success_notice: str = "") -> int:
    return await show_matched_order(update, context, success_notice=success_notice)

async def handle_sheet_update_error(update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception, action_description: str = "cập nhật ô") -> int:
    """Helper xử lý lỗi chung khi cập nhật Google Sheet."""
    logger.error(f"Lỗi khi {action_description}: {error}", exc_info=True) # Thêm exc_info=True để ghi traceback
    await show_order_after_edit(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
    return ConversationHandler.END # Kết thúc conversation khi có lỗi sheet