# config.py
import logging

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token của bot Telegram
BOT_TOKEN = "7469424189:AAH0xQDx0B2avI6sgVuegghd_EE7I-DZdzA"

# Tên của Google Sheet
SHEET_NAME = "Bảng Nhập Đơn"

# Trạng thái hội thoại cho ConversationHandler
TEN_SP, THONG_TIN_SP, TEN_KH, SLOT, SO_NGAY, NGUON, GIA_BAN, NOTE = range(8)
