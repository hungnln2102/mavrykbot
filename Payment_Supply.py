from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputFile
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from utils import connect_to_sheet
from datetime import datetime
from menu import show_outer_menu
import requests
from io import BytesIO
from column import SUPPLY_COLUMNS, SHEETS, ORDER_COLUMNS
import logging
import gspread
import re
import asyncio
import urllib.parse

logger = logging.getLogger(__name__)

def load_bank_map() -> dict:
    """Tải danh sách ngân hàng từ sheet 'Bank_List' và chuyển thành dictionary."""
    try:
        spreadsheet = connect_to_sheet()
        bank_sheet = spreadsheet.worksheet(SHEETS["BANK_LIST"])
        records = bank_sheet.get_all_values()[1:]
        return {row[0].strip(): row[1].strip() for row in records if row and row[0]}
    except Exception as e:
        logger.error(f"Không thể tải danh sách ngân hàng từ Google Sheets: {e}")
        return {}

def escape_mdv2(text: str) -> str:
    if not isinstance(text, str): text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def clean_price_string(price_str: str) -> str:
    if not isinstance(price_str, str): price_str = str(price_str)
    return price_str.replace(",", "").replace(".", "").replace("đ", "").replace("₫", "").strip()

def build_qr_url(stk: str, bank_code: str, amount, note: str) -> str:
    try:
        amount_int = int(clean_price_string(amount))
        note_encoded = urllib.parse.quote(note.strip())
        return f"https://img.vietqr.io/image/{bank_code}-{stk}-compact2.png?amount={amount_int}&addInfo={note_encoded}"
    except (ValueError, TypeError):
        raise ValueError(f"Tổng tiền không hợp lệ: {amount}")

def fetch_qr_image_bytes(url: str) -> bytes:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        if "image" not in response.headers.get("Content-Type", ""):
            raise ValueError("Dữ liệu trả về không phải ảnh hợp lệ.")
        return response.content
    except requests.RequestException as e:
        raise ValueError(f"Lỗi khi tải ảnh QR: {e}")

def get_current_time_column(header: list):
    today = datetime.now().date()
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

def calculate_actual_sum(ten_nguon: str, order_data_cache: list) -> int:
    total = 0
    target_nguon = ten_nguon.strip().lower().lstrip('@')
    for row in order_data_cache[1:]:
        try:
            nguon_don = row[ORDER_COLUMNS["NGUON"]].strip().lower().lstrip('@')
            check_don = row[ORDER_COLUMNS["CHECK"]].strip().lower()
            if nguon_don == target_nguon and check_don == "false":
                gia_nhap_clean_str = clean_price_string(row[ORDER_COLUMNS["GIA_NHAP"]])
                if gia_nhap_clean_str:
                    total += int(gia_nhap_clean_str)
        except (IndexError, ValueError, TypeError):
            continue
    return total

async def show_source_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int = 0):
    query = update.callback_query
    if query:
        await query.answer()

    bank_map = load_bank_map()

    if "payment_unpaid_sources" not in context.user_data:
        if query:
            try: 
                await query.edit_message_text("⏳ Đang tải dữ liệu từ Google Sheets, vui lòng chờ...")
            except BadRequest: 
                pass
        try:
            spreadsheet = connect_to_sheet()
            supply_sheet = spreadsheet.worksheet(SHEETS["SUPPLY"])
            supply_data = supply_sheet.get_all_values()
            order_sheet = spreadsheet.worksheet(SHEETS["ORDER"])
            order_data = order_sheet.get_all_values()
            context.user_data['payment_order_data_cache'] = order_data
            col_index, current_range = get_current_time_column(supply_data[0])
            if col_index is None:
                await query.edit_message_text(escape_mdv2("❌ Không tìm thấy cột thời gian phù hợp."), parse_mode="MarkdownV2")
                return
            unpaid_sources = []
            for i, row in enumerate(supply_data[1:], start=2):
                if col_index < len(row) and "đã thanh toán" not in row[col_index].lower() and row[col_index].strip():
                    unpaid_sources.append({"data": row, "row_index": i})
            context.user_data["payment_unpaid_sources"] = unpaid_sources
            context.user_data["payment_range"] = current_range
            context.user_data["payment_col_index"] = col_index
        except Exception as e:
            logger.error(f"Lỗi tải dữ liệu thanh toán: {e}")
            await query.edit_message_text(escape_mdv2(f"❌ Lỗi tải dữ liệu: {e}"), parse_mode="MarkdownV2")
            return

    unpaid_sources = context.user_data.get("payment_unpaid_sources", [])
    if not unpaid_sources or not (0 <= index < len(unpaid_sources)):
        final_text = "✅ Tuyệt vời! Đã xử lý xong tất cả các nguồn.\n\n_Tự động quay về menu sau 3 giây..._"
        try:
            await query.message.edit_text(escape_mdv2(final_text), parse_mode="MarkdownV2")
        except BadRequest:
            await query.message.delete()
            await update.effective_chat.send_message(text=escape_mdv2(final_text), parse_mode="MarkdownV2")
        await asyncio.sleep(3)
        await handle_exit_to_main(update, context)
        return

    context.user_data["payment_current_index"] = index
    source_info = unpaid_sources[index]
    row_data, col_index = source_info["data"], context.user_data["payment_col_index"]
    
    ten_nguon = row_data[SUPPLY_COLUMNS["TEN_NGUON"]]
    thong_tin = row_data[SUPPLY_COLUMNS["THONG_TIN_THANH_TOAN"]]
    tong_tien_expected_str = row_data[col_index]
    
    order_data_cache = context.user_data.get("payment_order_data_cache", [])
    actual_sum = calculate_actual_sum(ten_nguon, order_data_cache)
    try:
        expected_sum = int(clean_price_string(tong_tien_expected_str))
    except (ValueError, TypeError):
        expected_sum = -1

    lines = thong_tin.strip().split("\n")
    stk, bank_code = (lines[0].strip() if lines else "", lines[1].strip() if len(lines) > 1 else "")
    
    bank_name = bank_map.get(bank_code, bank_code)

    ten_nguon_md = escape_mdv2(ten_nguon)
    tong_tien_md = escape_mdv2(tong_tien_expected_str)
    stk_md = escape_mdv2(stk)
    bank_display_md = escape_mdv2(f"{bank_name} ({bank_code})")
    time_range_md = escape_mdv2(context.user_data['payment_range'])

    caption = (
        f"🏦 *Tên nguồn:* {ten_nguon_md}\n"
        f"💰 *Tổng tiền cần thanh toán:* {tong_tien_md}\n"
        f"🔢 *STK/Inick:* `{stk_md}`\n"
        f"🏦 *Ngân hàng:* {bank_display_md}\n"
        f"📆 *Thời gian:* {time_range_md}"
    )
    if actual_sum != expected_sum:
        actual_sum_formatted = f"{actual_sum:,} đ"
        caption += f"\n\n⚠️ *Lưu ý:* Tổng giá nhập thực tế là `{escape_mdv2(actual_sum_formatted)}`, không khớp với số tiền cần thanh toán."
    try:
        qr_url = build_qr_url(stk, bank_code, tong_tien_expected_str, ten_nguon)
        logger.info(f"QR URL tạo ra: {qr_url}")
        qr_bytes = fetch_qr_image_bytes(qr_url)
        qr_image = BytesIO(qr_bytes)
        qr_image.seek(0)
        photo_input = InputFile(qr_image, filename="qrcode.png")
    except Exception as e:
        logger.warning(f"Lỗi tạo QR cho {ten_nguon}: {e}. Hiển thị logo thay thế.")
        try:
            with open("logo_mavryk.jpg", "rb") as f:
                photo_input = InputFile(f, filename="logo.png")
        except Exception as fe:
            logger.error(f"Không thể load logo fallback: {fe}")
            blank_gif = BytesIO(
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
                b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
                b"\x00\x00\x02\x02D\x01\x00;"
            )
            blank_gif.seek(0)
            photo_input = InputFile(blank_gif, filename="blank.gif")

    nav_buttons = []
    if index > 0: nav_buttons.append(InlineKeyboardButton("◀️ Trước", callback_data=f"source_prev|{index}"))
    if index < len(unpaid_sources) - 1: nav_buttons.append(InlineKeyboardButton("Sau ▶️", callback_data=f"source_next|{index}"))
    keyboard = []
    if nav_buttons: keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("✅ Đã Thanh Toán", callback_data=f"source_paid|{index}"), InlineKeyboardButton("🔚 Kết thúc", callback_data="exit_to_main")])

    try:
        await query.message.edit_media(
            media=InputMediaPhoto(media=photo_input, caption=caption, parse_mode="MarkdownV2"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except BadRequest as e:
        if "Message is not modified" in str(e): 
            await query.answer("Nội dung không thay đổi.")
        else:
            await query.message.delete()
            await update.effective_chat.send_photo(
                photo=photo_input,
                caption=caption,
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Lỗi không xác định khi show_source_payment: {e}")
        await query.edit_message_text(escape_mdv2(f"❌ Lỗi: {e}"), parse_mode="MarkdownV2")


async def handle_source_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Đang xử lý...", show_alert=False)
    index = int(query.data.split("|")[1])

    unpaid_sources = context.user_data.get("payment_unpaid_sources", [])
    col_index = context.user_data.get("payment_col_index")
    order_data_cache = context.user_data.get("payment_order_data_cache", [])
    source_info = unpaid_sources[index]
    row_idx_supply, row_supply = source_info["row_index"], source_info["data"]
    ten_nguon = row_supply[SUPPLY_COLUMNS["TEN_NGUON"]]
    try:
        expected_sum = int(clean_price_string(row_supply[col_index]))
    except (ValueError, TypeError):
        await query.answer("❌ Số tiền thanh toán không hợp lệ.", show_alert=True)
        return

    unpaid_orders_of_source = []
    for i, row in enumerate(order_data_cache[1:], start=2):
        try:
            if (row[ORDER_COLUMNS["NGUON"]].strip().lower().lstrip('@') == ten_nguon.strip().lower().lstrip('@') and 
                row[ORDER_COLUMNS["CHECK"]].strip().lower() == "false"):
                unpaid_orders_of_source.append({"data": row, "row_index": i})
        except IndexError: 
            continue

    def get_date(order):
        try: 
            return datetime.strptime(order["data"][ORDER_COLUMNS["NGAY_DANG_KY"]], "%d/%m/%Y")
        except (ValueError, IndexError): 
            return datetime.max

    unpaid_orders_of_source.sort(key=get_date)

    current_sum, orders_to_pay_indices = 0, []
    for order in unpaid_orders_of_source:
        try:
            gia_nhap_clean_str = clean_price_string(order["data"][ORDER_COLUMNS["GIA_NHAP"]])
            if gia_nhap_clean_str:
                gia_nhap = int(gia_nhap_clean_str)
                if current_sum + gia_nhap <= expected_sum:
                    current_sum += gia_nhap
                    orders_to_pay_indices.append(order["row_index"])
                    if current_sum == expected_sum: 
                        break
        except (ValueError, IndexError, TypeError): 
            continue

    if current_sum != expected_sum:
        await query.answer(
            f"❌ Không tìm thấy tổ hợp đơn có tổng bằng {expected_sum:,} đ. "
            f"Tổng gần nhất là {current_sum:,} đ.", 
            show_alert=True
        )
        return

    try:
        spreadsheet = connect_to_sheet()
        supply_sheet = spreadsheet.worksheet(SHEETS["SUPPLY"])
        order_sheet = spreadsheet.worksheet(SHEETS["ORDER"])
        supply_sheet.update_cell(
            row_idx_supply, 
            col_index + 1, 
            f"Đã Thanh Toán (Tổng thực tế: {current_sum:,})\n{row_supply[col_index]}"
        )
        if orders_to_pay_indices:
            cells_to_update_q = [
                gspread.Cell(row=i, col=ORDER_COLUMNS["CHECK"] + 1, value="TRUE") 
                for i in orders_to_pay_indices
            ]
            order_sheet.update_cells(cells_to_update_q, value_input_option='USER_ENTERED')
        await query.answer("✅ Đã thanh toán thành công cho các đơn hàng khớp!", show_alert=True)
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật sheet cho nguồn {ten_nguon}: {e}")
        await query.answer("❌ Lỗi khi cập nhật Google Sheet.", show_alert=True)
        return

    unpaid_sources.pop(index)
    context.user_data["payment_unpaid_sources"] = unpaid_sources
    await show_source_payment(update, context, index=index)


async def handle_source_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, index_str = query.data.split("|")
    index = int(index_str)
    if action == "source_next":
        new_index = index + 1
    else:  # source_prev
        new_index = index - 1
    await show_source_payment(update, context, index=new_index)


async def handle_exit_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    for key in list(context.user_data.keys()):
        if key.startswith("payment_"):
            context.user_data.pop(key)
    await show_outer_menu(update, context)