# app/utils.py
import os, json, logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _creds_path():
    # cố định tới app/creds.json, kể cả chạy dưới NSSM
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "creds.json")

def service_account_email():
    with open(_creds_path(), "r", encoding="utf-8") as f:
        return json.load(f).get("client_email")

def _client():
    creds = Credentials.from_service_account_file(_creds_path(), scopes=SCOPES)
    return gspread.authorize(creds)

def _spreadsheet_id():
    # ưu tiên env; có thể fallback sang config nếu bạn có
    sid = os.getenv("SPREADSHEET_ID")
    if sid:
        return sid
    try:
        from config import SHEET_ID as sid_from_cfg  # nếu bạn có
        return sid_from_cfg
    except Exception:
        pass
    try:
        # fallback cuối: mở theo tên (kém ổn định)
        from config import SHEET_NAME as name
        return None if not name else ("NAME:" + name)
    except Exception:
        return None

def connect_to_sheet():
    """
    Trả về gspread.Spreadsheet đã mở sẵn.
    - Nếu có SPREADSHEET_ID: open_by_key
    - Nếu không: (fallback) open theo tên SHEET_NAME
    """
    client = _client()
    sid = _spreadsheet_id()
    if not sid:
        raise RuntimeError(
            "Chưa cấu hình SPREADSHEET_ID (nên đặt env hoặc SHEET_ID trong config.py)."
        )
    try:
        if sid.startswith("NAME:"):
            name = sid.split("NAME:", 1)[1]
            return client.open(name)
        return client.open_by_key(sid)
    except Exception as e:
        logger.error("Lỗi kết nối Google Sheet: %s", e, exc_info=True)
        raise

def append_to_sheet(sheet_name: str, data: list):
    sh = connect_to_sheet()
    ws = sh.worksheet(sheet_name)
    ws.append_row(data, value_input_option="USER_ENTERED")
    logger.info("✅ Đã ghi thành công vào sheet '%s'", sheet_name)

def generate_unique_id(sheet, loai_khach: str):
    import random, string
    loai_khach = (loai_khach or "").strip().lower()
    prefix = "MAVC" if loai_khach == "ctv" else "MAVL"
    while True:
        order_id = f"{prefix}{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
        if order_id not in sheet.col_values(1):
            return order_id

def escape_mdv2(text: str) -> str:
    import re
    if not isinstance(text, str):
        text = str(text)
    return re.sub(r'([_\*\[\]\(\)~`>\#\+\-\=\|\{\}\.!])', r'\\\1', text)

def gen_mavn_id():
    """Sinh ID MAVNxxxxx không trùng giữa Bảng Đơn Hàng & Bảng Nhập Hàng."""
    from column import SHEETS  # tránh import sớm gây circular
    ss = connect_to_sheet()
    order_ws = ss.worksheet(SHEETS["ORDER"])
    import_ws = ss.worksheet(SHEETS["IMPORT"])
    used = set([x.strip() for x in order_ws.col_values(1)[1:] if x]) \
         | set([x.strip() for x in import_ws.col_values(1)[1:] if x])

    n = 1
    while True:
        cand = f"MAVN{n:05d}"
        if cand not in used:
            return cand
        n += 1

def compute_dates(so_ngay: int, start_date: datetime | None = None):
    """Tính (ngày đăng ký, hết hạn, còn lại)."""
    tz_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_date or tz_today
    end = start + timedelta(days=int(so_ngay))
    con_lai = (end - tz_today).days
    fmt = lambda d: d.strftime("%d/%m/%Y")
    return fmt(start), fmt(end), max(con_lai, 0)

def to_int(v, default=0):
    """Chuyển chuỗi chứa tiền tệ hoặc ký tự sang int an toàn."""
    if v is None:
        return default
    s = str(v)
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else default