import os, json, logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import re
import time 
import http.client
from gspread.exceptions import APIError
from google.auth.exceptions import TransportError
from urllib3.exceptions import ProtocolError
from requests.exceptions import ConnectionError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

VN_TZ = timezone(timedelta(hours=7))

def _creds_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "creds.json")

def service_account_email():
    with open(_creds_path(), "r", encoding="utf-8") as f:
        return json.load(f).get("client_email")

def _client():
    creds = Credentials.from_service_account_file(_creds_path(), scopes=SCOPES)
    return gspread.authorize(creds)

def _spreadsheet_id():
    sid = os.getenv("SPREADSHEET_ID")
    if sid:
        return sid
    try:
        from config import SHEET_ID as sid_from_cfg
        return sid_from_cfg
    except Exception:
        pass
    try:
        from config import SHEET_NAME as name
        return None if not name else ("NAME:" + name)
    except Exception:
        return None

def connect_to_sheet(retries=3, delay=5):
    last_exception = None
    
    RETRYABLE_EXCEPTIONS = (
        TransportError,
        APIError,
        ConnectionError,
        ProtocolError,
        http.client.RemoteDisconnected
    )
    
    for i in range(retries):
        try:
            logger.debug(f"Đang kết nối Google Sheet (lần {i+1}/{retries})...")
            client = _client()
            sid = _spreadsheet_id()
            if not sid:
                raise RuntimeError("Lỗi cấu hình: SPREADSHEET_ID chưa được thiết lập.")
            spreadsheet = None
            if sid.startswith("NAME:"):
                name = sid.split("NAME:", 1)[1]
                spreadsheet = client.open(name)
            else:
                spreadsheet = client.open_by_key(sid)
            logger.info(f"Kết nối Google Sheet thành công (ID: {sid}).")
            return spreadsheet
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            logger.warning(f"Lỗi kết nối/API Google Sheet (lần {i+1}/{retries}): {e}")
            if i < retries - 1:
                logger.info(f"Đang thử lại sau {delay} giây...")
                time.sleep(delay)
            else:
                logger.error(f"Kết nối Google Sheet thất bại sau {retries} lần thử.")
        except RuntimeError as e:
            logger.error(str(e))
            raise
        except Exception as e:
            logger.error(f"Lỗi không xác định khi kết nối Sheet: {e}", exc_info=True)
            last_exception = e
            break
    
    if last_exception:
        logger.error(f"Không thể kết nối Google Sheet sau {retries} lần. Lỗi cuối: {last_exception}")
        raise last_exception

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
    if not isinstance(text, str):
        text = str(text)
    return re.sub(r'([_\*\[\]\(\)~`>\#\+\-\=\|\{\}\.!])', r'\\\1', text)

def gen_mavn_id():
    from column import SHEETS
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
    tz_today = datetime.now(VN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_date or tz_today
    end = start + timedelta(days=int(so_ngay))
    con_lai = (end - tz_today).days
    fmt = lambda d: d.strftime("%d/%m/%Y")
    return fmt(start), fmt(end), max(con_lai, 0)

def to_int(v, default=0):
    if v is None:
        return default
    s = str(v)
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else default

def format_date_dmy(date_obj):
    """Định dạng ngày thành 'dd/mm/yyyy'."""
    return date_obj.strftime("%d/%m/%Y")

def get_current_cycle_header_string():
    now = datetime.now(VN_TZ)
    days_until_sunday = (6 - now.weekday() + 7) % 7
    sunday_boundary_date = now.date() + timedelta(days=days_until_sunday)
    sunday_boundary = datetime(
        sunday_boundary_date.year, 
        sunday_boundary_date.month, 
        sunday_boundary_date.day, 
        19, 0, 0,
        tzinfo=VN_TZ
    )

    if now > sunday_boundary:
        cycle_end_date = sunday_boundary + timedelta(days=7)
    else:
        cycle_end_date = sunday_boundary
    cycle_start_date = cycle_end_date - timedelta(days=6)

    start_str = format_date_dmy(cycle_start_date.date())
    end_str = format_date_dmy(cycle_end_date.date())
    
    return f"{start_str} - {end_str}"

def normalize_product_duration(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    s = re.sub(r"[\u2010-\u2015]", "-", text)
    s = re.sub(r"-+\s*(\d+)\s*m\b", r"--\1m", s, flags=re.I)
    return s

def chuan_hoa_gia(text):
    try:
        s = str(text).lower().strip()
        is_thousand_k = 'k' in s
        has_separator = '.' in s
        digits = ''.join(filter(str.isdigit, s))
        if not digits:
            return "0", 0 
        number = int(digits)
        if is_thousand_k:
            number *= 1000
        elif not is_thousand_k and not has_separator and number < 5000:
            number *= 1000
        return "{:,}".format(number), number
    except (ValueError, TypeError):
        return "0", 0