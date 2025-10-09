import asyncio
import logging
import re
import traceback
from aiohttp import web
from telegram import Bot

# --- Import các thành phần từ file khác ---
from utils import connect_to_sheet
from column import SHEETS
from renewal_logic import run_renewal
from telegram_bot import send_renewal_success_notification # Sẽ tạo ở bước sau

logger = logging.getLogger(__name__)

# Bí mật này dùng để tạo ra đường dẫn webhook duy nhất
WEBHOOK_SECRET = "ef3ff711d58d498aa6147d60eb3923df"

def extract_ma_don(text: str):
    """Trích xuất các mã đơn hàng duy nhất từ nội dung."""
    if not text: return []
    return list(set(re.findall(r"MAV\w{5,}", text)))

def process_payment(bot: Bot, payment_data: dict):
    """
    Hàm xử lý nền: Ghi biên lai, kích hoạt gia hạn, và gửi thông báo.
    """
    try:
        content = payment_data.get("content", "")
        ma_don_list = extract_ma_don(content)
        ma_don_str = " - ".join(ma_don_list) if ma_don_list else ""

        # 1. GHI BIÊN LAI VÀO GOOGLE SHEET
        logger.info(f"Bắt đầu xử lý webhook cho giao dịch: '{content}'")
        sheet_receipt = connect_to_sheet().worksheet(SHEETS["RECEIPT"])
        new_row_values = [
            ma_don_str,
            payment_data.get("transactionDate", ""),
            payment_data.get("transferAmount", ""),
            payment_data.get("accountNumber", ""),
            content
        ]
        sheet_receipt.append_row(new_row_values)
        logger.info(f"✅ Ghi biên lai thành công cho: {ma_don_str or 'Giao dịch không có mã đơn'}")

        # 2. KÍCH HOẠT GIA HẠN (NẾU CÓ MÃ ĐƠN)
        if not ma_don_list:
            logger.info("Không tìm thấy mã đơn hàng, kết thúc xử lý.")
            return

        logger.info(f"Tìm thấy {len(ma_don_list)} mã đơn. Bắt đầu gia hạn...")
        for ma_don in ma_don_list:
            logger.info(f"--> Đang xử lý gia hạn cho mã: {ma_don}")
            success, details = run_renewal(ma_don)
            
            if success:
                logger.info(f"✅ GIA HẠN THÀNH CÔNG cho mã {ma_don}.")
                # Gọi hàm gửi thông báo (async) từ trong hàm sync
                asyncio.run(send_renewal_success_notification(bot, details))
            else:
                logger.error(f"❌ GIA HẠN THẤT BẠI cho mã {ma_don}. Lý do: {details}")
                # (Tùy chọn) Gửi thông báo lỗi cho admin
                # asyncio.run(send_error_notification(bot, f"Lỗi gia hạn mã {ma_don}: {details}"))

    except Exception:
        logger.error("❌ Lỗi nghiêm trọng trong hàm process_payment:")
        traceback.print_exc()

async def handle_payment(request: web.Request):
    """
    Hàm lắng nghe (async): Nhận request từ Sepay và đưa vào hàng chờ xử lý.
    """
    bot = request.app['bot']  # Lấy đối tượng bot từ main.py
    try:
        data = await request.json()
        # Đẩy việc xử lý nặng vào một luồng riêng để trả về phản hồi 200 cho Sepay ngay lập tức
        asyncio.create_task(
            asyncio.to_thread(process_payment, bot, data)
        )
        return web.Response(text="Webhook received", status=200)
    except Exception as e:
        logger.error(f"❌ Lỗi khi nhận webhook: {e}")
        return web.Response(text="Bad Request", status=400)

# Dòng này được import và sử dụng bởi main.py để thêm route vào web server
routes = web.RouteTableDef()
routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")(handle_payment)