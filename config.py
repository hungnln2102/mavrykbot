import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    logger.critical("LỖI BẢO MẬT: Không tìm thấy TELEGRAM_TOKEN trong file .env!")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if not ADMIN_CHAT_ID:
    logger.warning("Không tìm thấy ADMIN_CHAT_ID trong .env, dùng giá trị mặc định.")
    ADMIN_CHAT_ID = "510811276"

def get_env_bool(var_name, default=False):
    value = os.getenv(var_name, str(default)).lower()
    return value in ['true', '1', 't', 'y', 'yes']

SEND_RENEWAL_TO_TOPIC = get_env_bool("SEND_RENEWAL_TO_TOPIC", True)
RENEWAL_GROUP_ID = os.getenv("RENEWAL_GROUP_ID")

try:
    RENEWAL_TOPIC_ID = int(os.getenv("RENEWAL_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("RENEWAL_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 2")
    RENEWAL_TOPIC_ID = 2

SEND_ERROR_TO_TOPIC = get_env_bool("SEND_ERROR_TO_TOPIC", True)
ERROR_GROUP_ID = os.getenv("ERROR_GROUP_ID")
try:
    ERROR_TOPIC_ID = int(os.getenv("ERROR_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("ERROR_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 6")
    ERROR_TOPIC_ID = 6

DUE_ORDER_GROUP_ID = os.getenv("DUE_ORDER_GROUP_ID")
try:
    DUE_ORDER_TOPIC_ID = int(os.getenv("DUE_ORDER_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("DUE_ORDER_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 12")
    DUE_ORDER_TOPIC_ID = 12
    
SHEET_NAME = "Bảng Nhập Đơn"
TEN_SP, THONG_TIN_SP, TEN_KH, SLOT, SO_NGAY, NGUON, GIA_BAN, NOTE = range(8)

logger.info("Cấu hình đã được tải thành công.")
logger.info(f"Gửi thông báo gia hạn tới Topic: {SEND_RENEWAL_TO_TOPIC}")
logger.info(f"Gửi thông báo lỗi tới Topic: {SEND_ERROR_TO_TOPIC}")