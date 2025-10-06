from aiohttp import web
from utils import connect_to_sheet
from column import SHEETS
import re
import traceback
import asyncio
import logging

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = "ef3ff711d58d498aa6147d60eb3923df"

def extract_ma_don(text):
    return re.findall(r"MAV\w{5,}", text)

def save_receipt_to_sheet(payment_data: dict):
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

async def handle_payment(request: web.Request):

    try:
        data = await request.json()
        asyncio.create_task(
            asyncio.to_thread(save_receipt_to_sheet, data)
        )
        return web.Response(text="Webhook received", status=200)
    except Exception as e:
        logger.error(f"❌ Lỗi ngay khi nhận webhook (ví dụ: request không phải JSON): {e}")
        return web.Response(text="Bad Request", status=400)

routes = web.RouteTableDef()
routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")(handle_payment)
