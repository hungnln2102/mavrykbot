from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest
from utils import connect_to_sheet
from datetime import datetime
from menu import show_outer_menu
import requests
from io import BytesIO
from column import SUPPLY_COLUMNS, SHEETS, ORDER_COLUMNS

def build_qr_url(stk: str, bank_code: str, amount, note: str) -> str:
    """Tạo URL ảnh QR thanh toán VietQR."""
    if amount is None:
        raise ValueError("Tổng tiền không được để trống.")
    # Làm sạch và chuẩn hoá số tiền
    amount_str = str(amount).replace(",", "").replace(".", "").replace("đ", "").replace("₫", "").strip()
    if not amount_str.isdigit():
        raise ValueError(f"Tổng tiền không hợp lệ: {amount}")
    amount_int = int(amount_str)
    return f"https://img.vietqr.io/image/{bank_code}-{stk}-compact2.png?amount={amount_int}&addInfo={note}"

def fetch_qr_image_bytes(url: str) -> bytes:
    """Tải ảnh QR từ URL và trả về dưới dạng bytes."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"❌ Lỗi khi tải ảnh QR: {e}")

    if "image" not in response.headers.get("Content-Type", ""):
        raise ValueError("❌ Dữ liệu không phải ảnh hợp lệ.")

    return response.content

def get_current_time_column(sheet):
    """Duyệt dòng 1 của sheet để tìm cột có thời gian bao gồm ngày hôm nay.
        Trả về (index, tiêu đề cột) nếu tìm thấy."""
    today = datetime.now().date()
    header = sheet.row_values(1)

    for idx, val in enumerate(header):
        if "/" in val and "-" in val:
            try:
                start_str, end_str = val.split("-")
                start_date = datetime.strptime(start_str.strip(), "%d/%m/%Y").date()
                end_date = datetime.strptime(end_str.strip(), "%d/%m/%Y").date()
                if start_date <= today <= end_date:
                    return idx, val.strip()
            except ValueError:
                continue
    return None, None

async def show_source_payment(update, context: ContextTypes.DEFAULT_TYPE, index=0):
    unpaid_sources = context.user_data.get("payment_unpaid_sources")
    current_range = context.user_data.get("payment_range")
    col_index = context.user_data.get("payment_col_index")

    sheet = connect_to_sheet().worksheet(SHEETS["SUPPLY"])
    if unpaid_sources is None or current_range is None or col_index is None:
        col_index, current_range = get_current_time_column(sheet)
        data = sheet.get_all_values()[1:]
        unpaid_sources = []
        for i, row in enumerate(data):
            if col_index < len(row):
                value = row[col_index]
                if "đã thanh toán" not in value.lower() and value.strip():
                    unpaid_sources.append((i + 2, row))  # Dòng trong sheet
        context.user_data["payment_unpaid_sources"] = unpaid_sources
        context.user_data["payment_range"] = current_range
        context.user_data["payment_col_index"] = col_index

    if index < 0 or index >= len(unpaid_sources):
        try:
            qr_msg_id = context.user_data.get("qr_msg_id")
            if qr_msg_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=qr_msg_id)
        except Exception as e:
            print(f"[⚠️ Không thể xóa QR cũ]: {e}")

        try:
            if update.callback_query:
                await update.callback_query.message.delete()
        except:
            pass

        await update.effective_chat.send_message("✅ Không còn đơn hàng nào cần thanh toán.")
        await show_outer_menu(update, context)
        return

    row_idx, row = unpaid_sources[index]
    ten_nguon = row[SUPPLY_COLUMNS["TEN_NGUON"]] if len(row) > SUPPLY_COLUMNS["TEN_NGUON"] else ""
    thong_tin = row[SUPPLY_COLUMNS["SO_TK"]] if len(row) > SUPPLY_COLUMNS["SO_TK"] else ""
    tong_tien = row[col_index] if col_index < len(row) else ""

    if isinstance(thong_tin, list):
        thong_tin = "".join(map(str, thong_tin))

    lines = thong_tin.strip().split("\n")
    stk = lines[0].strip() if len(lines) >= 1 else ""
    bank_code = lines[1].strip().upper() if len(lines) >= 2 else ""

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"source_prev|{index}"))
    if index < len(unpaid_sources) - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"source_next|{index}"))

    keyboard = [
        nav_buttons,
        [
            InlineKeyboardButton("✅ Đã Thanh Toán", callback_data=f"source_paid|{index}"),
            InlineKeyboardButton("🌾 Kết Thúc", callback_data="exit_to_main")
        ]
    ]

    caption = (
        f"🏦 *Tên nguồn:* {ten_nguon}\n"
        f"📆 *Thời gian:* {current_range}\n"
        f"💰 *Tổng thanh toán:* {tong_tien}\n"
        f"🔢 *STK/Inick:* `{stk}`\n"
        f"🏦 *Ngân hàng:* {bank_code}"
    )

    try:
        qr_url = build_qr_url(stk, bank_code, tong_tien, ten_nguon)
        qr_bytes = fetch_qr_image_bytes(qr_url)
        qr_image = BytesIO(qr_bytes)
        qr_image.name = "qr.png"
    except Exception:
        with open("logo_mavryk.jpg", "rb") as f:
            qr_image = BytesIO(f.read())
            qr_image.name = "logo.jpg"
        caption += "\n⚠️ *Không thể tạo mã QR, hiển thị logo thay thế.*"

    try:
        msg = update.callback_query.message if update.callback_query else None
        if msg and msg.photo:
            await msg.edit_media(
                media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="Markdown"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            if msg:
                await msg.delete()
            sent_msg = await update.effective_chat.send_photo(
                photo=qr_image,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data["qr_msg_id"] = sent_msg.message_id
    except BadRequest as e:
        if "Message is not modified" in str(e):
            print("[⚠️ Bỏ qua vì nội dung trùng lặp]")
        else:
            await update.effective_chat.send_message(f"❌ Không thể gửi ảnh: {e}")

async def handle_exit_to_main(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except:
        pass

    # Clear cached data
    context.user_data.pop("payment_data", None)
    context.user_data.pop("payment_col_index", None)
    context.user_data.pop("payment_range", None)
    context.user_data.pop("qr_msg_id", None)

    await show_outer_menu(update, context)

async def handle_source_paid(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("|")[1])

    unpaid_sources = context.user_data.get("payment_unpaid_sources", [])
    col_index = context.user_data.get("payment_col_index")

    if index >= len(unpaid_sources) or col_index is None:
        await query.message.reply_text("❌ Không tìm thấy thông tin cần thiết.")
        return

    # ✅ Lấy dữ liệu dòng nguồn
    row_idx, row = unpaid_sources[index]
    ten_nguon = row[SUPPLY_COLUMNS["TEN_NGUON"]]

    # ✅ Cập nhật trạng thái thanh toán trong sheet "Thông Tin Nguồn"
    sheet_nguon = connect_to_sheet().worksheet(SHEETS["SUPPLY"])
    cell_value = sheet_nguon.cell(row_idx, col_index + 1).value
    if cell_value and "đã thanh toán" not in cell_value.lower():
        sheet_nguon.update_cell(row_idx, col_index + 1, f"Đã Thanh Toán\n{cell_value}")

    # ✅ Tìm và tick các đơn thuộc nguồn này trong "Bảng Đơn Hàng"
    sheet_don = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data_don = sheet_don.get_all_values()
    for i, row_don in enumerate(data_don[1:], start=2):  # Bỏ dòng tiêu đề
        nguon = row_don[ORDER_COLUMNS["NGUON"]] if len(row_don) > ORDER_COLUMNS["NGUON"] else ""
        check = row_don[ORDER_COLUMNS["CHECK"]] if len(row_don) > ORDER_COLUMNS["CHECK"] else ""
        if nguon == ten_nguon and check.strip().lower() == "false":
            sheet_don.update_cell(i, ORDER_COLUMNS["CHECK"] + 1, True)

    # ✅ Xoá nguồn đã xử lý khỏi danh sách
    unpaid_sources.pop(index)
    context.user_data["payment_unpaid_sources"] = unpaid_sources

    # ✅ Chuyển sang nguồn kế tiếp
    if index >= len(unpaid_sources):
        index = max(0, len(unpaid_sources) - 1)

    await show_source_payment(update, context, index=index)

async def handle_source_navigation(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    action = data[0]
    index = int(data[1])

    if action == "source_next":
        await show_source_payment(update, context, index=index + 1)
    elif action == "source_prev":
        await show_source_payment(update, context, index=index - 1)