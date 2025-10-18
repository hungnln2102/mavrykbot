import logging
import os
from dotenv import load_dotenv

# === BẮT ĐẦU SỬA LỖI ĐƯỜNG DẪN ===

# Lấy đường dẫn tuyệt đối của tệp config.py này
# Ví dụ: C:\srv\mavryk_store_bot\app\config.py
current_file_path = os.path.abspath(__file__)

# Lấy đường dẫn của thư mục chứa tệp này (thư mục 'app')
# Ví dụ: C:\srv\mavryk_store_bot\app
app_dir = os.path.dirname(current_file_path)

# Lấy đường dẫn của thư mục cha (thư mục gốc của dự án)
# Ví dụ: C:\srv\mavryk_store_bot
project_root = os.path.dirname(app_dir)

# Tạo đường dẫn đầy đủ đến tệp .env
# Ví dụ: C:\srv\mavryk_store_bot\.env
dotenv_path = os.path.join(project_root, '.env')

# --- Tải biến môi trường từ đường dẫn CHÍNH XÁC ---
load_dotenv(dotenv_path=dotenv_path)

# === KẾT THÚC SỬA LỖI ĐƯỜNG DẪN ===


# --- Cấu hình Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Cấu hình Bot & Bảo mật ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    logger.critical("LỖI BẢO MẬT: Không tìm thấy TELEGRAM_TOKEN trong file .env!")
    logger.critical(f"Đã tìm tệp .env tại: {dotenv_path}") # Thêm log để kiểm tra

# --- Cấu hình Admin & Thông báo ---
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if not ADMIN_CHAT_ID:
    logger.warning("Không tìm thấy ADMIN_CHAT_ID trong .env, dùng giá trị mặc định.")
    ADMIN_CHAT_ID = "510811276" # Giá trị dự phòng

# Hàm helper để đọc giá trị boolean ("true", "false") từ .env
def get_env_bool(var_name, default=False):
    value = os.getenv(var_name, str(default)).lower()
    return value in ['true', '1', 't', 'y', 'yes']

# Cấu hình thông báo GIA HẠN
SEND_RENEWAL_TO_TOPIC = get_env_bool("SEND_RENEWAL_TO_TOPIC", True)
RENEWAL_GROUP_ID = os.getenv("RENEWAL_GROUP_ID")
try:
    RENEWAL_TOPIC_ID = int(os.getenv("RENEWAL_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("RENEWAL_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 2")
    RENEWAL_TOPIC_ID = 2 # Giá trị dự phòng

# Cấu hình thông báo LỖI
SEND_ERROR_TO_TOPIC = get_env_bool("SEND_ERROR_TO_TOPIC", True)
ERROR_GROUP_ID = os.getenv("ERROR_GROUP_ID")
try:
    ERROR_TOPIC_ID = int(os.getenv("ERROR_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("ERROR_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 6")
    ERROR_TOPIC_ID = 6 # Giá trị dự phòng

# Cấu hình thông báo ĐƠN SẮP HẾT HẠN
DUE_ORDER_GROUP_ID = os.getenv("DUE_ORDER_GROUP_ID")
try:
    DUE_ORDER_TOPIC_ID = int(os.getenv("DUE_ORDER_TOPIC_ID"))
except (ValueError, TypeError):
    logger.warning("DUE_ORDER_TOPIC_ID không hợp lệ, dùng giá trị mặc định là 12")
    DUE_ORDER_TOPIC_ID = 12 # Giá trị dự phòng


# --- Cấu hình Google Sheet ---
SHEET_NAME = "Bảng Nhập Đơn"
TEN_SP, THONG_TIN_SP, TEN_KH, SLOT, SO_NGAY, NGUON, GIA_BAN, NOTE = range(8)


# Log kiểm tra khi khởi động
logger.info("Cấu hình đã được tải thành công.")
logger.info(f"Đang tìm .env tại: {dotenv_path}")
logger.info(f"Gửi thông báo gia hạn tới Topic: {SEND_RENEWAL_TO_TOPIC}")
logger.info(f"Gửi thông báo lỗi tới Topic: {SEND_ERROR_TO_TOPIC}")