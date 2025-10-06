import logging
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.critical("LỖI BẢO MẬT: Không tìm thấy token trong file .env!")
SHEET_NAME = "Bảng Nhập Đơn"
TEN_SP, THONG_TIN_SP, TEN_KH, SLOT, SO_NGAY, NGUON, GIA_BAN, NOTE = range(8)