import random
import re
import string
import gspread
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from config import SHEET_NAME, logger

# Kết nối với Google Sheets – trả về toàn bộ spreadsheet
def connect_to_sheet():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(os.environ["GOOGLE_CREDS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        return spreadsheet
    except Exception as e:
        logger.error(f"Lỗi kết nối đến Google Sheet: {str(e)}")
        raise
def append_to_sheet(sheet_name: str, data: list):
    """Ghi một dòng dữ liệu mới vào cuối một worksheet được chỉ định."""
    try:
        spreadsheet = connect_to_sheet()
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.append_row(data, value_input_option='USER_ENTERED')
        logger.info(f"✅ Đã ghi thành công vào sheet '{sheet_name}'")
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"❌ Lỗi: Không tìm thấy worksheet có tên '{sheet_name}'")
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi khi ghi vào sheet '{sheet_name}': {e}")
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
        
def escape_mdv2(text: str) -> str:
    """Hàm escape các ký tự đặc biệt cho chế độ MarkdownV2 của Telegram."""
    if not isinstance(text, str):
        text = str(text)
    # Các ký tự đặc biệt cần escape trong MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)