from aiohttp import web
from utils import connect_to_sheet
from column import SHEETS
import re
import traceback

WEBHOOK_SECRET = "b9d02dd9510d4570a9d176bc401f4754"


def extract_ma_don(text):
    match = re.search(r"MAV\w{5,}", text)
    return match.group(0) if match else None


routes = web.RouteTableDef()


@routes.post(f"/api/payment/notify/{WEBHOOK_SECRET}")
async def handle_payment(request):
    try:
        data = await request.json()
        content = data.get("content", "")
        ma_don = extract_ma_don(content)

        sheet = connect_to_sheet().worksheet(SHEETS["RECEIPT"])
        values = [
            ma_don or "",
            data.get("transactionDate", ""),
            data.get("transferAmount", ""),
            data.get("accountNumber", ""),
            content
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
