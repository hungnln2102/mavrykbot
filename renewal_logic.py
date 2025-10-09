import logging
import re
from datetime import datetime, timedelta

# Import các thành phần từ file khác trong dự án của bạn
from utils import connect_to_sheet
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX

# --- Các hàm phụ trợ ---
def tinh_ngay_het_han(ngay_dang_ky_str, so_ngay_str):
    try:
        start_date = datetime.strptime(ngay_dang_ky_str, "%d/%m/%Y")
        num_days = int(so_ngay_str)
        end_date = start_date + timedelta(days=num_days)
        return end_date.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""

def chuan_hoa_gia(text):
    try:
        s = str(text).lower().strip()
        is_thousand = 'k' in s
        digits = ''.join(filter(str.isdigit, s))
        if not digits: return "0", 0
        number = int(digits)
        if is_thousand: number *= 1000
        return "{:,}".format(number), number
    except (ValueError, TypeError):
        return "0", 0

def normalize_product_duration(text: str) -> str:
    if not isinstance(text, str): text = str(text)
    s = re.sub(r"[\u2010-\u2015]", "-", text)
    s = re.sub(r"-+\s*(\d+)\s*m\b", r"--\1m", s, flags=re.I)
    return s

logger = logging.getLogger(__name__)

def run_renewal(order_id: str):
    """
    Chỉ tự động gia hạn cho đơn hàng có số ngày còn lại <= 4.
    Tất cả các trường hợp khác sẽ bị bỏ qua.
    Luôn trả về 3 giá trị: (success, details, process_type)
    """
    if not order_id:
        return False, "Mã đơn hàng không được để trống.", "error"

    try:
        # 1. TÌM ĐƠN HÀNG
        ws_order = connect_to_sheet().worksheet(SHEETS["ORDER"])
        all_orders = ws_order.get_all_values()
        
        order_info = None
        for i, row in enumerate(all_orders[1:], start=2):
            if len(row) > ORDER_COLUMNS["ID_DON_HANG"] and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == order_id.strip():
                order_info = {"data": row, "row_index": i}
                break
        
        if not order_info:
            logger.warning(f"Không tìm thấy đơn hàng với mã {order_id}")
            return False, f"Không tìm thấy đơn hàng {order_id}", "error"

        row_data, row_idx = order_info["data"], order_info["row_index"]

        # 2. KIỂM TRA SỐ NGÀY CÒN LẠI
        try:
            so_ngay_con_lai = int(row_data[ORDER_COLUMNS["CON_LAI"]])
        except (ValueError, IndexError):
            so_ngay_con_lai = 0

        # 3. QUYẾT ĐỊNH XỬ LÝ
        if so_ngay_con_lai <= 4:
            # --- TIẾN HÀNH GIA HẠN ---
            logger.info(f"Đơn {order_id} đủ điều kiện gia hạn ({so_ngay_con_lai} ngày). Bắt đầu xử lý...")
            
            san_pham = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
            ngay_cuoi_cu = row_data[ORDER_COLUMNS["HET_HAN"]].strip()
            nguon_hang = row_data[ORDER_COLUMNS["NGUON"]].strip()
            gia_nhap_cu = row_data[ORDER_COLUMNS["GIA_NHAP"]].strip()
            gia_ban_cu = row_data[ORDER_COLUMNS["GIA_BAN"]].strip()

            san_pham_norm = normalize_product_duration(san_pham)
            match_thoi_han = re.search(r"--\s*(\d+)\s*m", san_pham_norm, flags=re.I)
            if not match_thoi_han:
                return False, f"Không thể xác định thời hạn từ '{san_pham}'.", "error"

            so_thang = int(match_thoi_han.group(1))
            so_ngay_gia_han = 365 if so_thang == 12 else so_thang * 30

            start_dt = datetime.strptime(ngay_cuoi_cu, "%d/%m/%Y") + timedelta(days=1)
            ngay_bat_dau_moi = start_dt.strftime("%d/%m/%Y")
            ngay_het_han_moi = tinh_ngay_het_han(ngay_bat_dau_moi, str(so_ngay_gia_han))
            
            gia_nhap_moi, gia_ban_moi = None, None
            try:
                sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
                ty_gia_data = sheet_ty_gia.get_all_values()
                headers = [h.strip() for h in (ty_gia_data[0] if ty_gia_data else [])]
                is_ctv = order_id.upper().startswith("MAVC")
                nguon_col_idx = headers.index(nguon_hang) if nguon_hang in headers else -1

                product_row_data = next((r for r in ty_gia_data[1:] if len(r) > TYGIA_IDX["SAN_PHAM"] and r[TYGIA_IDX["SAN_PHAM"]].strip().lower() == san_pham.lower()), None)
                
                if product_row_data:
                    gia_ban_col = TYGIA_IDX["GIA_CTV"] if is_ctv else TYGIA_IDX["GIA_KHACH"]
                    _, gia_ban_moi = chuan_hoa_gia(product_row_data[gia_ban_col])
                    if nguon_col_idx != -1 and len(product_row_data) > nguon_col_idx:
                        _, gia_nhap_moi = chuan_hoa_gia(product_row_data[nguon_col_idx])
            except Exception as e:
                logger.warning(f"Không thể tra cứu giá mới cho {order_id}: {e}. Sẽ dùng giá cũ.")

            final_gia_nhap = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
            final_gia_ban = gia_ban_moi if gia_ban_moi is not None else chuan_hoa_gia(gia_ban_cu)[1]
            
            ws_order.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau_moi)
            ws_order.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, str(so_ngay_gia_han))
            ws_order.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi)
            ws_order.update_cell(row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, final_gia_nhap)
            ws_order.update_cell(row_idx, ORDER_COLUMNS["GIA_BAN"] + 1, final_gia_ban)

            updated_details = {
                "ID_DON_HANG": order_id, "SAN_PHAM": san_pham,
                "THONG_TIN_DON": row_data[ORDER_COLUMNS["THONG_TIN_DON"]],
                "SLOT": row_data[ORDER_COLUMNS["SLOT"]],
                "NGAY_DANG_KY": ngay_bat_dau_moi, "HET_HAN": ngay_het_han_moi,
                "NGUON": nguon_hang, "GIA_NHAP": final_gia_nhap, "GIA_BAN": final_gia_ban
            }
            return True, updated_details, "renewal"
        
        else:
            # --- BỎ QUA CÁC TRƯỜDE NG HỢP KHÁC ---
            logger.info(f"Đơn {order_id} còn nhiều ngày ({so_ngay_con_lai} ngày), bỏ qua thanh toán.")
            return False, "Bỏ qua do còn nhiều ngày", "skipped"

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi xử lý đơn {order_id}: {e}", exc_info=True)
        return False, f"Lỗi hệ thống: {e}", "error"