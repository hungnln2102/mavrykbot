# payment_webhook.py (Đã tối ưu để chống timeout)

from aiohttp import web
from utils import connect_to_sheet
from column import SHEETS
import re
import traceback
import asyncio
import logging

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = "b9d02dd9510d4570a9d176bc401f4754"

def extract_ma_don(text):
    """Lấy tất cả mã đơn theo định dạng MAVxxxxx trở lên."""
    return re.findall(r"MAV\w{5,}", text)

# --- Bước 1: Tạo hàm đồng bộ để xử lý tác vụ chậm (ghi vào Google Sheet) ---
def save_receipt_to_sheet(payment_data: dict):
    """
    Hàm này thực hiện việc kết nối và ghi dữ liệu vào Google Sheet.
    Nó được thiết kế để chạy trong một thread nền.
    """
    try:
        logger.info(f"Bắt đầu xử lý nền cho webhook: {payment_data.get('content')}")
        
        content = payment_data.get("content", "")
        ma_don_list = extract_ma_don(content)
        ma_don_str = " - ".join(ma_don_list) if ma_don_list else ""

        sheet = connect_to_sheet().worksheet(SHEETS["RECEIPT"])
        values = [
            ma_don_str,
            payment_data.get("transactionDate", ""),
            payment_data.get("transferAmount", ""),
            payment_data.get("accountNumber", ""),
            content
        ]
        sheet.append_row(values)

        logger.info(f"✅ Ghi biên lai thành công cho: {ma_don_str if ma_don_str else 'Không có mã đơn'}")

    except Exception:
        logger.error("❌ Lỗi khi xử lý nền webhook:")
        traceback.print_exc()

# --- Bước 2: Sửa lại hàm xử lý webhook để phản hồi ngay ---
async def handle_payment(request: web.Request):
    """
    Nhận webhook, phản hồi OK ngay lập tức, và đưa việc xử lý vào nền.
    """
    try:
        # 1. Nhận dữ liệu
        data = await request.json()

        # 2. Đưa tác vụ xử lý sheet vào nền để chạy.
        # Bot sẽ không chờ hàm này chạy xong.
        asyncio.create_task(
            asyncio.to_thread(save_receipt_to_sheet, data)
        )

        # 3. Trả về phản hồi "OK" ngay lập tức cho dịch vụ webhook
        return web.Response(text="Webhook received", status=200)

    except Exception as e:
        logger.error(f"❌ Lỗi ngay khi nhận webhook (ví dụ: request không phải JSON): {e}")
        return web.Response(text="Bad Request", status=400)

# --- Bước 3: Đăng ký route ---
# Biến 'routes' này sẽ được import vào file main.py
routes = web.RouteTableDef()
routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")(handle_payment)