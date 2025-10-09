import logging
import re
from datetime import datetime, timedelta

# Giả định: Các file này tồn tại trong dự án của bạn
from utils import connect_to_sheet
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX

# Nếu hàm tinh_ngay_het_han ở file khác thì import, nếu không thì định nghĩa ở đây
# Ví dụ lấy từ file add_order.py của bạn
def tinh_ngay_het_han(ngay_dang_ky_str, so_ngay_str):
    try:
        start_date = datetime.strptime(ngay_dang_ky_str, "%d/%m/%Y")
        num_days = int(so_ngay_str)
        end_date = start_date + timedelta(days=num_days)
        return end_date.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""

logger = logging.getLogger(__name__)

# --- CÁC HÀM PHỤ TRỢ (Lấy từ file update_order.py) ---

def chuan_hoa_gia(text):
    try:
        s = str(text).lower().strip()
        is_thousand = 'k' in s
        digits = ''.join(filter(str.isdigit, s))
        if not digits:
            return "0", 0
        number = int(digits)
        if is_thousand:
            number *= 1000
        return "{:,}".format(number), number
    except (ValueError, TypeError):
        return "0", 0

def normalize_product_duration(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # Chuẩn hóa các loại gạch ngang khác nhau về gạch ngang tiêu chuẩn
    s = re.sub(r"[\u2010-\u2015]", "-", text)
    # Đảm bảo định dạng là --<số>m, ví dụ "Spotify -1m" -> "Spotify --1m"
    s = re.sub(r"-+\s*(\d+)\s*m\b", r"--\1m", s, flags=re.I)
    return s

# --- HÀM GIA HẠN TỰ ĐỘNG CHÍNH ---

def run_renewal(order_id: str):
    """
    Tự động tìm và gia hạn cho một đơn hàng dựa trên ID của nó.
    Trả về một tuple: (success: bool, details: dict | str)
    Nếu thành công, details là một dictionary chứa thông tin đơn hàng đã cập nhật.
    Nếu thất bại, details là một chuỗi thông báo lỗi.
    """
    if not order_id:
        return False, "Mã đơn hàng không được để trống."

    try:
        # 1. KẾT NỐI VÀ TÌM ĐƠN HÀNG
        ws_order = connect_to_sheet().worksheet(SHEETS["ORDER"])
        all_orders = ws_order.get_all_values()
        
        order_info = None
        for i, row in enumerate(all_orders[1:], start=2): # Bắt đầu từ hàng 2
            if len(row) > ORDER_COLUMNS["ID_DON_HANG"] and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == order_id.strip():
                order_info = {"data": row, "row_index": i}
                break
        
        if not order_info:
            logger.warning(f"Không tìm thấy đơn hàng với mã {order_id}")
            return False, f"Không tìm thấy đơn hàng {order_id}"

        row_data, row_idx = order_info["data"], order_info["row_index"]

        # 2. TÍNH TOÁN THỜI GIAN GIA HẠN
        san_pham = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
        ngay_cuoi_cu = row_data[ORDER_COLUMNS["HET_HAN"]].strip()

        san_pham_norm = normalize_product_duration(san_pham)
        match_thoi_han = re.search(r"--\s*(\d+)\s*m", san_pham_norm, flags=re.I)
        
        if not match_thoi_han:
            return False, f"Không thể xác định thời hạn từ tên sản phẩm '{san_pham}'."

        so_thang = int(match_thoi_han.group(1))
        so_ngay_gia_han = 365 if so_thang == 12 else so_thang * 30

        start_dt = datetime.strptime(ngay_cuoi_cu, "%d/%m/%Y") + timedelta(days=1)
        ngay_bat_dau_moi = start_dt.strftime("%d/%m/%Y")
        ngay_het_han_moi = tinh_ngay_het_han(ngay_bat_dau_moi, str(so_ngay_gia_han))
        
        # 3. TRA CỨU GIÁ MỚI TỪ SHEET "TỶ GIÁ"
        nguon_hang = row_data[ORDER_COLUMNS["NGUON"]].strip()
        gia_nhap_cu = row_data[ORDER_COLUMNS["GIA_NHAP"]].strip()
        gia_ban_cu = row_data[ORDER_COLUMNS["GIA_BAN"]].strip()
        
        gia_nhap_moi, gia_ban_moi = None, None
        try:
            sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
            ty_gia_data = sheet_ty_gia.get_all_values()
            headers = [h.strip() for h in (ty_gia_data[0] if ty_gia_data else [])]
            is_ctv = order_id.upper().startswith("MAVC")
            
            nguon_col_idx = headers.index(nguon_hang) if nguon_hang in headers else -1

            product_row_data = None
            for r in ty_gia_data[1:]:
                if len(r) > TYGIA_IDX["SAN_PHAM"] and r[TYGIA_IDX["SAN_PHAM"]].strip().lower() == san_pham.lower():
                    product_row_data = r
                    break
            
            if product_row_data:
                gia_ban_col = TYGIA_IDX["GIA_CTV"] if is_ctv else TYGIA_IDX["GIA_KHACH"]
                _, gia_ban_moi = chuan_hoa_gia(product_row_data[gia_ban_col])
                if nguon_col_idx != -1 and len(product_row_data) > nguon_col_idx:
                    _, gia_nhap_moi = chuan_hoa_gia(product_row_data[nguon_col_idx])
        except Exception as e:
            logger.warning(f"Không thể tra cứu giá mới cho {order_id}: {e}. Sẽ dùng giá cũ.")

        final_gia_nhap = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
        final_gia_ban = gia_ban_moi if gia_ban_moi is not None else chuan_hoa_gia(gia_ban_cu)[1]
        
        # 4. CẬP NHẬT GOOGLE SHEET
        ws_order.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau_moi)
        ws_order.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, str(so_ngay_gia_han))
        ws_order.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi)
        ws_order.update_cell(row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, final_gia_nhap)
        ws_order.update_cell(row_idx, ORDER_COLUMNS["GIA_BAN"] + 1, final_gia_ban)

        logger.info(f"✅ Gia hạn thành công cho đơn hàng {order_id}.")

        # 5. TRẢ VỀ DỮ LIỆU ĐÃ CẬP NHẬT
        updated_details = {
            "ID_DON_HANG": order_id,
            "SAN_PHAM": san_pham,
            "THONG_TIN_DON": row_data[ORDER_COLUMNS["THONG_TIN_DON"]],
            "SLOT": row_data[ORDER_COLUMNS["SLOT"]],
            "NGAY_DANG_KY": ngay_bat_dau_moi,
            "HET_HAN": ngay_het_han_moi,
            "NGUON": nguon_hang,
            "GIA_NHAP": final_gia_nhap,
            "GIA_BAN": final_gia_ban
        }
        return True, updated_details

    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi gia hạn đơn {order_id}: {e}", exc_info=True)
        return False, f"Lỗi hệ thống: {e}"