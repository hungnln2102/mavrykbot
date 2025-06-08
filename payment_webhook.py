# payment_webhook.py
from aiohttp import web
from utils import connect_to_sheet
import re

WEBHOOK_SECRET = "b9d02dd9510d4570a9d176bc401f4754"  # Trùng với cấu hình trên SePay

routes = web.RouteTableDef()

def extract_ma_don(text):
    """Tìm mã đơn theo định dạng MAVxxxxx (ít nhất 5 ký tự sau MAV)"""
    match = re.search(r"MAV\w{5,}", text)
    return match.group(0) if match else None

@routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")
async def handle_payment(request):
    try:
        data = await request.json()
        content = data.get("content", "")
        ma_don = extract_ma_don(content)  # Có thể trả về None

        sheet = connect_to_sheet().worksheet("Biên Lai Thanh Toán")
        sheet.append_row([
            ma_don or "",                              # Cột A: Mã đơn hàng
            data.get("transactionDate", ""),          # Cột B: Ngày Thanh Toán
            data.get("transferAmount", ""),           # Cột C: Số tiền
            data.get("accountNumber", ""),            # Cột D: Người gửi (hiện là số tài khoản)
            content                                    # Cột E: Nội dung chuyển khoản
        ])

        if ma_don:
            return web.Response(text="✅ Ghi biên lai có mã đơn")
        else:
            return web.Response(text="⚠️ Ghi biên lai KHÔNG có mã đơn", status=200)

    except Exception as e:
        import traceback
        print("❌ Lỗi xử lý webhook SePay:")
        traceback.print_exc()
        return web.Response(text="❌ Lỗi server", status=500)
