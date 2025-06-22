from aiohttp import web
from utils import connect_to_sheet
from column import SHEETS
import re
import traceback

WEBHOOK_SECRET = "b9d02dd9510d4570a9d176bc401f4754"


def extract_ma_don(text):
    # Lấy tất cả mã đơn theo định dạng MAVxxxxx trở lên
    return re.findall(r"MAV\w{5,}", text)


routes = web.RouteTableDef()


@routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")
async def handle_payment(request):
    try:
        data = await request.json()
        content = data.get("content", "")
        ma_don_list = extract_ma_don(content)
        ma_don_str = " - ".join(ma_don_list) if ma_don_list else ""

        sheet = connect_to_sheet().worksheet(SHEETS["RECEIPT"])
        values = [
            ma_don_str,                                   # Cột A: Mã đơn (1 hoặc nhiều, cách nhau bằng " - ")
            data.get("transactionDate", ""),              # Cột B: Thời gian giao dịch
            data.get("transferAmount", ""),               # Cột C: Số tiền chuyển
            data.get("accountNumber", ""),                # Cột D: Số tài khoản
            content                                        # Cột E: Nội dung gốc
        ]
        sheet.append_row(values)

        return web.Response(text="✅ Ghi biên lai có mã đơn")

    except Exception as e:
        traceback.print_exc()
        return web.Response(text="❌ Lỗi server", status=500)


app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    web.run_app(app, port=8000)
