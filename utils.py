import random
import string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import SHEET_NAME, logger

# Kết nối với Google Sheets – trả về toàn bộ spreadsheet
def connect_to_sheet():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
        client = gspread.authorize(creds)

        spreadsheet = client.open(SHEET_NAME)  # ✅ Trả về cả file
        return spreadsheet
    except Exception as e:
        logger.error(f"Lỗi kết nối đến Google Sheet: {str(e)}")
        raise

# Tạo ID đơn hàng ngẫu nhiên không trùng lặp
def generate_unique_id(sheet, loai_khach: str):
    """
    Tạo mã đơn hàng duy nhất.
    - loai_khach: 'ctv' hoặc 'le' (phân biệt tiền tố MAVC hoặc MAVL)
    """
    loai_khach = loai_khach.strip().lower()
    prefix = "MAVC" if loai_khach == "ctv" else "MAVL"

    while True:
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        order_id = f"{prefix}{random_part}"
        
        # Kiểm tra mã đã tồn tại trong cột A chưa
        all_ids = sheet.col_values(1)
        if order_id not in all_ids:
            return order_id
