from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler
from utils import connect_to_sheet
from datetime import datetime
from menu import show_main_selector
import requests
from io import BytesIO

def build_qr_url(stk, bank_code, amount, note):
    amount_clean = str(amount).replace(".", "").replace(" đ", "").replace(",", "").strip()
    if not amount_clean.isdigit():
        raise ValueError("Tổng tiền không hợp lệ hoặc đang để trống.")
    amount_int = int(amount_clean)
    return f"https://img.vietqr.io/image/{bank_code}-{stk}-compact2.png?amount={amount_int}&addInfo={note}"

def fetch_qr_image_bytes(qr_url):
    response = requests.get(qr_url)
    if response.status_code != 200 or not response.headers['Content-Type'].startswith('image'):
        raise ValueError("QR URL không trả về file ảnh hợp lệ")
    return BytesIO(response.content)

def get_current_time_column(sheet):
    headers = sheet.row_values(1)
    today = datetime.today().date()

    for col_index in range(2, len(headers)):
        time_range = headers[col_index]
        try:
            start_str, end_str = [s.strip() for s in time_range.split("-")]
            start_date = datetime.strptime(start_str, "%d/%m/%Y").date()
            end_date = datetime.strptime(end_str, "%d/%m/%Y").date()
            if start_date <= today <= end_date:
                return col_index + 1, time_range
        except:
            continue

    raise ValueError("⛔️ Không tìm thấy khoảng thời gian nào phù hợp trong dòng 1.")

async def show_source_payment(update, context: ContextTypes.DEFAULT_TYPE, index=0):
    data = context.user_data.get("payment_data")
    col_index = context.user_data.get("payment_col_index")
    current_range = context.user_data.get("payment_range")

    if not data or not col_index or not current_range:
        sheet = connect_to_sheet().worksheet("Thông Tin Nguồn")
        col_index, current_range = get_current_time_column(sheet)
        data = sheet.get_all_values()[1:]
        context.user_data["payment_data"] = data
        context.user_data["payment_col_index"] = col_index
        context.user_data["payment_range"] = current_range

    if index < 0 or index >= len(data):
        try:
            qr_msg_id = context.user_data.get("qr_msg_id")
            if qr_msg_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=qr_msg_id)
        except Exception as e:
            print(f"[⚠️ Không thể xóa QR cũ]: {e}")

        try:
            await update.callback_query.message.delete()
        except:
            pass

        await update.effective_chat.send_message("✅ Không còn đơn hàng nào cần thanh toán.")
        await show_main_selector(update, context)
        return

    row = data[index]
    ten_nguon = row[0]
    thong_tin = row[1]
    tong_tien = row[col_index - 1] if col_index - 1 < len(row) else ""

    if "đã thanh toán" in tong_tien.lower() or not tong_tien.strip():
        await show_source_payment(update, context, index=index + 1)
        return

    try:
        lines = thong_tin.strip().split("\n")
        stk = lines[0].strip()
        bank_code = lines[1].strip().upper()
    except Exception as e:
        await update.callback_query.message.reply_text(f"⚠️ Lỗi đọc thông tin nguồn: {e}")
        return

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"source_prev|{index}"))
    if index < len(data) - 1:
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
        qr_image = fetch_qr_image_bytes(qr_url)
    except Exception:
        with open("logo_mavryk.jpg", "rb") as f:
            qr_image = BytesIO(f.read())
            qr_image.name = "logo.jpg"
        caption += "\n⚠️ *Không thể tạo mã QR, hiển thị logo thay thế.*"
    else:
        qr_image.name = "qr.png"

    try:
        if update.callback_query.message.photo:
            await update.callback_query.message.edit_media(
                media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="Markdown"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.callback_query.message.delete()
            msg = await update.effective_chat.send_photo(
                photo=qr_image,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data["qr_msg_id"] = msg.message_id
    except Exception as e:
        await update.callback_query.message.reply_text(f"❌ Không thể gửi ảnh: {e}")


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

    await show_main_selector(update, context)


async def handle_source_paid(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    index = int(data[1])

    spreadsheet = connect_to_sheet()
    sheet_nguon = spreadsheet.worksheet("Thông Tin Nguồn")
    col_index = context.user_data.get("payment_col_index")
    ten_nguon = sheet_nguon.cell(index + 2, 1).value.strip()

    sheet_don = spreadsheet.worksheet("Bảng Đơn Hàng")
    data_don = sheet_don.get_all_values()
    for i, row in enumerate(data_don[1:], start=2):
        nguon = row[10].strip() if len(row) > 10 else ""
        trang_thai = row[16].strip().lower() if len(row) > 16 else ""
        if nguon == ten_nguon and trang_thai == "false":
            sheet_don.update_cell(i, 17, True)

    cell_value = sheet_nguon.cell(index + 2, col_index).value
    if cell_value and "đã thanh toán" not in cell_value.lower():
        new_value = f"Đã Thanh Toán\n{cell_value}"
        sheet_nguon.update_cell(index + 2, col_index, new_value)

    await show_source_payment(update, context, index=index + 1)


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