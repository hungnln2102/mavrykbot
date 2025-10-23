import logging
import gspread
import threading
import traceback
from gspread.utils import rowcol_to_a1

# Import các module tùy chỉnh
from utils import connect_to_sheet, get_current_cycle_header_string
from column import SHEETS, ORDER_COLUMNS

logger = logging.getLogger(__name__)

def update_supply_cost(ma_don: str, lock: threading.Lock):
    """
    Cập nhật chi phí nhập hàng vào sheet "Thông Tin Nguồn" 
    dựa trên một mã đơn hàng.
    """
    try:
        logger.info(f"[SupplyCost] Bắt đầu cập nhật chi phí cho {ma_don}")
        
        # 1. Kết nối Google Sheet
        client = connect_to_sheet()
        sheet_order = client.worksheet(SHEETS["ORDER"])
        sheet_supply = client.worksheet(SHEETS["SUPPLY"])

        # 2. Tìm mã đơn hàng trong "Bảng Đơn Hàng"
        try:
            cell = sheet_order.find(
                ma_don, 
                in_column=ORDER_COLUMNS["ID_DON_HANG"] + 1 # gspread dùng index 1-based
            )
        except gspread.exceptions.CellNotFound:
            cell = None
        
        if not cell:
            logger.warning(f"[SupplyCost] Không tìm thấy {ma_don} trong {SHEETS['ORDER']}.")
            return False

        # 3. Lấy thông tin Nguồn và Giá Nhập từ hàng tìm được
        row_data = sheet_order.row_values(cell.row)
        
        if len(row_data) <= max(ORDER_COLUMNS["NGUON"], ORDER_COLUMNS["GIA_NHAP"]):
            logger.error(f"[SupplyCost] Hàng {cell.row} của {ma_don} thiếu dữ liệu.")
            return False

        nguon = row_data[ORDER_COLUMNS["NGUON"]]
        gia_nhap_str = row_data[ORDER_COLUMNS["GIA_NHAP"]]

        try:
            # Làm sạch giá trị (loại bỏ "đ", ".", ",")
            gia_nhap = float(gia_nhap_str.lower().replace('đ', '').replace('.', '').replace(',', '').strip() or 0)
        except (ValueError, IndexError):
            logger.warning(f"[SupplyCost] {ma_don} có Giá Nhập không hợp lệ: '{gia_nhap_str}'")
            return False

        if not nguon or gia_nhap == 0:
            logger.info(f"[SupplyCost] {ma_don} không có Nguồn ('{nguon}') hoặc Giá Nhập = 0.")
            return False

        logger.info(f"[SupplyCost] Tìm thấy: {ma_don} | Nguồn: {nguon} | Giá: {gia_nhap}")

        # 4. Xác định chu kỳ ngày (Gọi hàm từ utils.py)
        cycle_header = get_current_cycle_header_string()
        
        # 5. Khóa để bắt đầu cập nhật sheet SUPPLY
        with lock:
            logger.debug(f"[SupplyCost] Đã chiếm khóa (lock) cho {ma_don}")
            
            # 6. Tìm hàng (Nguồn) và cột (Chu kỳ)
            all_nguon_names = sheet_supply.col_values(1) # Lấy tất cả Cột A
            try:
                row_index = all_nguon_names.index(nguon) + 1 # gspread dùng index 1-based
            except ValueError:
                logger.error(f"[SupplyCost] Không tìm thấy tên nguồn '{nguon}' ở Cột A của {SHEETS['SUPPLY']}.")
                return False # Thoát khỏi 'with' và hàm

            all_cycle_headers = sheet_supply.row_values(1) # Lấy tất cả Dòng 1
            try:
                col_index = all_cycle_headers.index(cycle_header) + 1 # gspread dùng index 1-based
            except ValueError:
                # Không tìm thấy cột -> Tạo cột mới
                logger.info(f"[SupplyCost] Không tìm thấy chu kỳ '{cycle_header}'. Đang tạo cột mới...")
                col_index = len(all_cycle_headers) + 1
                sheet_supply.update_cell(1, col_index, cycle_header)

            # 7. Cập nhật giá trị
            current_value_str = sheet_supply.cell(row_index, col_index).value or "0"
            try:
                current_value = float(current_value_str.lower().replace('đ', '').replace('.', '').replace(',', '').strip())
            except ValueError:
                current_value = 0.0

            new_value = current_value + gia_nhap
            
            cell_to_update = rowcol_to_a1(row_index, col_index)
            sheet_supply.update_acell(cell_to_update, new_value)
            
            logger.info(f"[SupplyCost] Cập nhật thành công {nguon} tại {cycle_header} (Ô {cell_to_update}): {current_value} -> {new_value}")
        
        # Khóa được tự động nhả ở đây
        logger.debug(f"[SupplyCost] Đã nhả khóa (lock) cho {ma_don}")
        return True

    except gspread.exceptions.APIError as e:
        logger.error(f"❌ [SupplyCost] Lỗi API Google Sheet khi xử lý {ma_don}: {e}")
        return False
    except Exception:
        logger.error(f"❌ [SupplyCost] Lỗi nghiêm trọng khi xử lý {ma_don}:")
        traceback.print_exc() # In chi tiết lỗi
        return False