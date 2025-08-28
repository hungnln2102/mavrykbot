# config.py (Phiên bản an toàn)

import logging
import os
from dotenv import load_dotenv

# Lệnh này sẽ tìm và tải các biến từ file .env trong cùng thư mục
load_dotenv()

# --- CÁC THAY ĐỔI CHÍNH BẮT ĐẦU TỪ ĐÂY ---

# 1. Đọc token từ biến môi trường có tên "TELEGRAM_TOKEN"
#    Giá trị này được lấy từ file .env của bạn
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- KẾT THÚC THAY ĐỔI ---


# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. Thêm kiểm tra để đảm bảo bot không chạy nếu thiếu token
if not BOT_TOKEN:
    logger.critical("LỖI BẢO MẬT: Không tìm thấy token trong file .env!")
    # Bạn có thể bỏ comment dòng dưới để chương trình dừng lại nếu không có token
    # exit()


# Tên của Google Sheet
SHEET_NAME = "Bảng Nhập Đơn"

# Trạng thái hội thoại cho ConversationHandler
TEN_SP, THONG_TIN_SP, TEN_KH, SLOT, SO_NGAY, NGUON, GIA_BAN, NOTE = range(8)