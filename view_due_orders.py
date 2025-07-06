# view_due_orders.py (Hoàn thiện cuối cùng)

import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from utils import connect_to_sheet, escape_mdv2
from add_order import tinh_ngay_het_han
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from menu import show_outer_menu
from collections import OrderedDict
from column import SHEETS, ORDER_COLUMNS, PRICE_COLUMNS
import logging
import asyncio

# Cấu hình logging
logger = logging.getLogger(__name__)


def clean_price_to_amount(text):
    """Chuyển đổi chuỗi giá thành số nguyên."""
    return int(str(text).replace(",", "").replace(".", "").replace("₫", "").replace("đ", "").replace(" ", ""))

async def view_expired_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu quy trình, tải và cache toàn bộ dữ liệu cần thiết."""
    query = update.callback_query
    await query.answer("Đang tải dữ liệu, vui lòng chờ...")

    try:
        spreadsheet = connect_to_sheet()
        order_sheet = spreadsheet.worksheet(SHEETS["ORDER"])
        price_sheet = spreadsheet.worksheet(SHEETS["PRICE"])
        
        all_orders_data = order_sheet.get_all_values()
        price_list_data = price_sheet.get_all_values()
        
        if len(all_orders_data) <= 1:
            await query.edit_message_text(escape_mdv2("✅ Không có dữ liệu đơn hàng nào."), parse_mode="MarkdownV2")
            return

    except Exception as e:
        logger.error(f"Lỗi khi tải dữ liệu từ Google Sheet: {e}")
        await query.edit_message_text(escape_mdv2("❌ Đã xảy ra lỗi khi tải dữ liệu từ Google Sheet."), parse_mode="MarkdownV2")
        return

    rows = all_orders_data[1:]
    expired_orders = OrderedDict()
    
    for i, row in enumerate(rows, start=2):
        if not any(cell.strip() for cell in row): continue
        try:
            con_lai_val = float(row[ORDER_COLUMNS["CON_LAI"]].strip())
            ma_don = row[ORDER_COLUMNS["ID_DON_HANG"]].strip()
            if ma_don and con_lai_val <= 4:
                expired_orders[ma_don] = {"data": row, "row_index": i}
        except (ValueError, IndexError):
            continue

    if not expired_orders:
        await query.edit_message_text(escape_mdv2("✅ Hiện không có đơn hàng nào sắp hết hạn."))
        return

    context.user_data["expired_orders"] = expired_orders
    context.user_data["price_list_data"] = price_list_data
    context.user_data["expired_index"] = 0
    
    await show_expired_order(update, context, direction="stay")

def get_gia_ban(ma_don, ma_san_pham, banggia_data, gia_ban_donhang=None):
    """Lấy giá bán chính xác từ dữ liệu cache."""
    ma_sp = str(ma_san_pham).strip().replace("–", "--").replace("—", "--")
    is_ctv = str(ma_don).upper().startswith("MAVC")

    for row in banggia_data[1:]:
        if len(row) <= max(PRICE_COLUMNS["GIA_BAN_CTV"], PRICE_COLUMNS["GIA_BAN_LE"]): continue
        sp_goc = str(row[PRICE_COLUMNS["TEN_SAN_PHAM"]]).strip().replace("–", "--").replace("—", "--")
        if sp_goc == ma_sp:
            try:
                gia_str = row[PRICE_COLUMNS["GIA_BAN_CTV"]] if is_ctv else row[PRICE_COLUMNS["GIA_BAN_LE"]]
                gia = clean_price_to_amount(gia_str)
                if gia > 0: return gia
            except Exception as e:
                logger.warning(f"[Lỗi parse giá trong bảng giá]: {e}")
            break
    
    if isinstance(gia_ban_donhang, list): gia_ban_donhang = gia_ban_donhang[0] if gia_ban_donhang else ""
    return clean_price_to_amount(gia_ban_donhang) if gia_ban_donhang else 0

def build_order_caption(row: list, price_list_data: list, index: int, total: int):
    """Tạo caption cho đơn hàng, có kèm bộ đếm và escape ký tự triệt để."""
    def get_val(col_name):
        try: return row[ORDER_COLUMNS[col_name]].strip()
        except (IndexError, KeyError): return ""
    
    ma_don_raw, product_raw = get_val("ID_DON_HANG"), get_val("SAN_PHAM")
    con_lai_raw = get_val("CON_LAI")
    
    days_left = int(float(con_lai_raw)) if con_lai_raw and con_lai_raw.replace('.', '', 1).isdigit() else 0
    gia_int = get_gia_ban(ma_don_raw, product_raw, price_list_data, row[ORDER_COLUMNS["GIA_BAN"]])
    gia_value_raw = "{:,} đ".format(gia_int) if gia_int > 0 else "Chưa xác định"

    product_md = escape_mdv2(product_raw)
    ma_don_md = escape_mdv2(ma_don_raw)
    info_md = escape_mdv2(get_val("THONG_TIN_DON"))
    ten_khach_md = escape_mdv2(get_val("TEN_KHACH"))
    link_khach_md = escape_mdv2(get_val("LINK_KHACH"))
    slot_md = escape_mdv2(get_val("SLOT"))
    ngay_dang_ky_md = escape_mdv2(get_val("NGAY_DANG_KY"))
    so_ngay_md = escape_mdv2(get_val("SO_NGAY"))
    ngay_het_han_md = escape_mdv2(get_val("HET_HAN"))
    gia_md = escape_mdv2(gia_value_raw)

    try:
        amount = clean_price_to_amount(gia_value_raw)
        qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={ma_don_raw}&accountName=NGO%20LE%20NGOC%20HUNG"
        response = requests.get(qr_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        qr_image = BytesIO(response.content)
    except Exception as e:
        logger.error(f"Lỗi tạo QR: {e}")
        qr_image = BytesIO()
        Image.new("RGB", (256, 256), "white").save(qr_image, "PNG")

    if days_left <= 0: status_line = f"⛔️ Đã hết hạn {abs(days_left)} ngày trước"
    else: status_line = f"⏳ Còn lại {days_left} ngày"
    
    header = (
        f"📦 *Đơn hàng đến hạn* `({index + 1}/{total})`\n"
        f"*{escape_mdv2('Sản phẩm:')}* {product_md}\n"
        f"*{escape_mdv2('Mã đơn:')}* `{ma_don_md}`\n"
        f"{escape_mdv2(status_line)}"
    )
    body = (
        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"📝 *Mô tả:* {info_md}\n" +
        (f"🧩 *Slot:* {slot_md}\n" if get_val("SLOT") else "") +
        (f"📅 Ngày đăng ký: {ngay_dang_ky_md}\n" if get_val("NGAY_DANG_KY") else "") +
        f"⏳ *Thời hạn:* {so_ngay_md} ngày\n"
        f"⏳ *Ngày hết hạn:* {ngay_het_han_md}\n"
        f"💵 *Giá bán:* {gia_md}\n\n"
        f"━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
        f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        f"🔸 *Tên:* {ten_khach_md}\n" +
        (f"🔗 *Liên hệ:* {link_khach_md}\n" if get_val("LINK_KHACH") else "")
    )
    footer = (
        escape_mdv2("━━━━━━━━━━━━━━━━━━━━━━\n") +
        escape_mdv2("💬 Để duy trì dịch vụ liên tục, quý khách nên gia hạn trước ngày hết hạn.\n") +
        escape_mdv2("📎 Quý khách vui lòng thanh toán kèm theo mã đơn hàng để dễ dàng đối chiếu.\n") +
        escape_mdv2("✨ Trân trọng cảm ơn quý khách!\n") + "\u200b"
    )
    return f"{header}\n{escape_mdv2('━━━━━━━━━━━━━━━━━━━━━━')}\n{body}\n{footer}", qr_image

async def extend_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gia hạn đơn hàng, thông báo bằng alert và hiển thị đơn tiếp theo từ cache."""
    query = update.callback_query
    await query.answer("Đang gia hạn...")
    ma_don = query.data.split("|")[1].strip()

    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    order_info = orders.get(ma_don)
    
    if not order_info:
        await query.answer("❌ Lỗi: Không tìm thấy đơn hàng trong cache.", show_alert=True)
        return

    row_data, row_idx = order_info["data"], order_info["row_index"]
    
    # ... (Phần logic tính toán ngày và giá mới giữ nguyên)
    product = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
    matched = re.search(r"--(\d+)m", product)
    if not matched:
        await query.answer("⚠️ Không xác định được thời hạn từ sản phẩm.", show_alert=True)
        return
    so_thang = int(matched.group(1)); so_ngay = 365 if so_thang == 12 else so_thang * 30
    ngay_cu_str = row_data[ORDER_COLUMNS["HET_HAN"]].strip()
    try:
        dt_cu = datetime.strptime(ngay_cu_str, "%d/%m/%Y")
    except ValueError:
        await query.answer(f"⚠️ Định dạng ngày hết hạn '{ngay_cu_str}' không hợp lệ.", show_alert=True)
        return
    dt_moi = dt_cu + timedelta(days=1)
    ngay_bat_dau_moi = dt_moi.strftime("%d/%m/%Y")
    ngay_het_han_moi = tinh_ngay_het_han(ngay_bat_dau_moi, str(so_ngay))
    price_list_data = context.user_data.get("price_list_data", [])
    gia_ban_moi = get_gia_ban(ma_don, product, price_list_data, row_data[ORDER_COLUMNS["GIA_BAN"]])

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        # Cập nhật các ô dữ liệu, bỏ qua ô công thức
        range_1 = f'G{row_idx}:I{row_idx}'
        values_1 = [[ngay_bat_dau_moi, str(so_ngay), ngay_het_han_moi]]
        sheet.update(range_1, values_1, value_input_option='USER_ENTERED')
        sheet.update_cell(row_idx, ORDER_COLUMNS["GIA_BAN"] + 1, str(gia_ban_moi))
        
        await query.answer("✅ Gia hạn thành công!", show_alert=True)
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật hàng loạt cho đơn {ma_don}: {e}")
        await query.answer("❌ Lỗi khi cập nhật Google Sheet.", show_alert=True)
        return

    # Cập nhật cache và hiển thị đơn tiếp theo
    orders.pop(ma_don)
    context.user_data["expired_orders"] = orders
    await show_expired_order(update, context, "stay")

async def show_expired_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    query = update.callback_query
    await query.answer()
    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    index: int = context.user_data.get("expired_index", 0)
    
    if not orders:
        await query.edit_message_text(escape_mdv2("✅ Không còn đơn hàng nào để hiển thị."))
        return

    keys, total_orders = list(orders.keys()), len(orders)
    if direction == "next": index += 1
    elif direction == "prev": index -= 1
    index = max(0, min(index, total_orders - 1))
    context.user_data["expired_index"] = index

    ma_don, order_info = keys[index], orders[keys[index]]
    price_list_data = context.user_data.get("price_list_data", [])
    caption, qr_image = build_order_caption(order_info["data"], price_list_data, index, total_orders)

    nav_buttons = []
    if index > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_expired"))
    if index < total_orders - 1: nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data="next_expired"))
    
    buttons = []
    if nav_buttons: buttons.append(nav_buttons)
    buttons.append([
        InlineKeyboardButton("🔄 Gia hạn", callback_data=f"extend_order|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa đơn", callback_data=f"delete_order_from_expired|{ma_don}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="back_to_menu_expired")
    ])
    reply_markup = InlineKeyboardMarkup(buttons)

    try:
        await query.message.edit_media(media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="MarkdownV2"), reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Lỗi edit_media, thử gửi mới: {e}")
        try: await query.message.delete()
        except: pass
        await query.message.chat.send_photo(photo=qr_image, caption=caption, parse_mode="MarkdownV2", reply_markup=reply_markup)

async def delete_order_from_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xóa đơn hàng, thông báo bằng alert và hiển thị đơn tiếp theo từ cache."""
    query = update.callback_query
    await query.answer("Đang xóa...")
    ma_don_to_delete = query.data.split("|")[1].strip()
    
    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    order_info = orders.get(ma_don_to_delete)
    
    if not order_info:
        await query.answer("❌ Lỗi: Không tìm thấy đơn hàng trong cache.", show_alert=True)
        return

    row_idx_to_delete = order_info.get("row_index")
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.delete_rows(row_idx_to_delete)
        await query.answer("🗑️ Xóa đơn hàng thành công!", show_alert=True)
    except Exception as e:
        logger.error(f"Lỗi khi xóa đơn {ma_don_to_delete}: {e}")
        await query.answer("❌ Lỗi khi xóa đơn trên Google Sheet.", show_alert=True)
        return
        
    # Cập nhật lại index của các đơn hàng còn lại trong cache
    updated_orders = OrderedDict()
    for key, value in orders.items():
        if key == ma_don_to_delete:
            continue
        current_row_index = value["row_index"]
        if current_row_index > row_idx_to_delete:
            value["row_index"] = current_row_index - 1
        updated_orders[key] = value

    context.user_data["expired_orders"] = updated_orders
    
    await show_expired_order(update, context, "stay")

async def back_to_menu_from_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dọn dẹp context và quay về menu chính."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("expired_orders", None)
    context.user_data.pop("price_list_data", None)
    context.user_data.pop("expired_index", None)
    await show_outer_menu(update, context)