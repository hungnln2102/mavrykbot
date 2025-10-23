import asyncio
import logging
import re
import traceback
import threading
# ⛔ ĐÃ XÓA import gspread
from aiohttp import web
from telegram import Bot

# Import các module tùy chỉnh của bạn
from utils import connect_to_sheet
from column import SHEETS
from renewal_logic import run_renewal
from supply_logic import update_supply_cost # 👈 IMPORT TỪ FILE MỚI
from telegram_bot import send_renewal_success_notification

logger = logging.getLogger(__name__)

# Bí mật webhook (giữ nguyên)
WEBHOOK_SECRET = "ef3ff711d58d498aa6147d60eb3923df"

# --- PHẦN MỚI: Khóa (Lock) ---
# Khóa này vẫn phải được định nghĩa ở đây (file chính) 
# để truyền vào hàm update_supply_cost
SUPPLY_SHEET_LOCK = threading.Lock()
# -----------------------------

def extract_ma_don(text: str):
    """(Giữ nguyên hàm này)"""
    if not text: return []
    return list(set(re.findall(r"MAV\w{5,}", text)))

# ⛔ ĐÃ XÓA hàm update_supply_cost (vì đã chuyển sang supply_logic.py)


# --- HÀM `process_payment` (Giữ nguyên) ---

def process_payment(bot: Bot, payment_data: dict, loop: asyncio.AbstractEventLoop):
    try:
        content = payment_data.get("content", "")
        ma_don_list = extract_ma_don(content)
        ma_don_str = " - ".join(ma_don_list) if ma_don_list else ""

        logger.info(f"Processing webhook for transaction: '{content}'")
        sheet_receipt = connect_to_sheet().worksheet(SHEETS["RECEIPT"])
        new_row_values = [
            ma_don_str,
            payment_data.get("transactionDate", ""),
            payment_data.get("transferAmount", ""),
            payment_data.get("accountNumber", ""),
            content
        ]
        sheet_receipt.append_row(new_row_values)
        logger.info(f"✅ Receipt logged successfully for: {ma_don_str or 'Transaction without order ID'}")

        if not ma_don_list:
            logger.info("No order ID found, ending process.")
            return

        for ma_don in ma_don_list:
            logger.info(f"--> Bắt đầu xử lý ID: {ma_don}")

            # --- LOGIC MỚI: Cập nhật chi phí nguồn ---
            # (Gọi hàm từ supply_logic.py)
            try:
                update_supply_cost(ma_don, SUPPLY_SHEET_LOCK)
            except Exception as e:
                logger.error(f"❌ Lỗi xảy ra khi gọi update_supply_cost cho {ma_don}: {e}")
            # --- KẾT THÚC LOGIC MỚI ---
            
            # --- LOGIC CŨ: Gia hạn (renewal) ---
            # (Gọi hàm từ renewal_logic.py)
            logger.info(f"[Renewal] Bắt đầu kiểm tra gia hạn cho {ma_don}")
            success, details, process_type = run_renewal(ma_don)

            if success and process_type == "renewal":
                logger.info(f"✅ RENEWAL SUCCESSFUL for ID {ma_don}.")
                asyncio.run_coroutine_threadsafe(
                    send_renewal_success_notification(bot, details),
                    loop
                )
            else:
                logger.info(f"[Renewal] Kết thúc xử lý ID {ma_on} với status '{process_type}'. Reason: {details}")

    except Exception:
        logger.error("❌ A critical error occurred in the process_payment function:")
        traceback.print_exc()
# -------------------------------------------------


# --- CÁC HÀM CÒN LẠI (GIỮ NGUYÊN) ---

async def handle_payment(request: web.Request):
    bot = request.app['bot']
    try:
        data = await request.json()

        current_loop = asyncio.get_running_loop()
        asyncio.create_task(
            asyncio.to_thread(
                process_payment,
                bot,
                data,
                current_loop
            )
        )
        return web.Response(text="Webhook received", status=200)
    except Exception as e:
        logger.error(f"❌ Error receiving webhook: {e}")
        return web.Response(text="Bad Request", status=400)

# Định tuyến (giữ nguyên)
routes = web.RouteTableDef()
routes.post(f"/bot/payment_sepay/{WEBHOOK_SECRET}")(handle_payment)