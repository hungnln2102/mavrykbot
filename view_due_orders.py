import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler
from utils import connect_to_sheet
from add_order import tinh_ngay_het_han
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from menu import show_main_selector
from collections import OrderedDict
from column import SHEETS, ORDER_COLUMNS, PRICE_COLUMNS

def escape_markdown(text):
    special_chars = r'\\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special_chars else c for c in str(text))

def clean_price_to_amount(text):
    return int(
        text.replace(",", "")
            .replace(".", "")
            .replace("₫", "")
            .replace("đ", "")
            .replace(" ", "")
    )

async def view_expired_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.callback_query.message.reply_text(
            escape_markdown("✅ Không có dữ liệu đơn hàng."),
            parse_mode="MarkdownV2"
        )
        await show_main_selector(update, context)
        return ConversationHandler.END

    rows = data[1:]
    expired_orders = OrderedDict()

    for row in rows:
        if not any(cell.strip() for cell in row):
            continue

        try:
            ma_don = row[ORDER_COLUMNS["ID_DON_HANG"]].strip()
            con_lai_str = row[ORDER_COLUMNS["CON_LAI"]].strip()
            con_lai_val = float(con_lai_str)
        except Exception:
            continue

        if ma_don and con_lai_val <= 4:
            expired_orders[ma_don] = {"data": row}

    if not expired_orders:
        await update.callback_query.message.reply_text(
            escape_markdown("✅ Hiện không có đơn hàng nào sắp hết hạn."),
            parse_mode="MarkdownV2"
        )
        await show_main_selector(update, context)
        return ConversationHandler.END

    context.user_data["expired_orders"] = expired_orders
    context.user_data["expired_index"] = 0
    await show_expired_order(update, context, direction="stay")

def clean_price_string(gia_str):
    return int(
        str(gia_str)
        .replace(",", "")
        .replace(".", "")
        .replace(" đ", "")
        .replace(" ₫", "")
        .replace("₫", "")
        .replace("đ", "")
        .strip()
    )

def get_gia_ban(ma_don, ma_san_pham, banggia_data, gia_ban_donhang=None):
    """
    Trả về giá bán ưu tiên theo bảng giá. Nếu không tìm được thì lấy từ đơn hàng.
    """
    ma_sp = ma_san_pham.strip().replace("–", "--").replace("—", "--")
    is_ctv = ma_don.upper().startswith("MAVC")

    for row in banggia_data[1:]:  # bỏ header
        if len(row) < max(PRICE_COLUMNS["GIA_BAN_CTV"], PRICE_COLUMNS["GIA_BAN_LE"]) + 1:
            continue

        sp_goc = row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip().replace("–", "--").replace("—", "--")
        if sp_goc == ma_sp:
            try:
                gia_str = row[PRICE_COLUMNS["GIA_BAN_CTV"]] if is_ctv else row[PRICE_COLUMNS["GIA_BAN_LE"]]
                gia = clean_price_to_amount(gia_str)
                if gia > 0:
                    return gia
            except:
                break

    # Nếu không tìm thấy → fallback về giá trong đơn hàng
    return clean_price_to_amount(gia_ban_donhang) if gia_ban_donhang else 0

def build_order_caption(row: list):
    # Lấy dữ liệu theo chỉ số
    ma_don = row[ORDER_COLUMNS["ID_DON_HANG"]].strip()
    product = row[ORDER_COLUMNS["SAN_PHAM"]].strip()
    thong_tin_don = row[ORDER_COLUMNS["THONG_TIN_DON"]].strip()
    ten_khach = row[ORDER_COLUMNS["TEN_KHACH"]].strip()
    link_khach = row[ORDER_COLUMNS["LINK_KHACH"]].strip()
    slot = row[ORDER_COLUMNS["SLOT"]].strip()
    ngay_dang_ky = row[ORDER_COLUMNS["NGAY_DANG_KY"]].strip()
    so_ngay = row[ORDER_COLUMNS["SO_NGAY"]].strip()
    ngay_het_han = row[ORDER_COLUMNS["HET_HAN"]].strip()
    con_lai = row[ORDER_COLUMNS["CON_LAI"]].strip()
    nguon = row[ORDER_COLUMNS["NGUON"]].strip()

    days_left = int(float(con_lai)) if con_lai else 0

    # Escape markdown
    product_md = escape_markdown(product)
    ma_don_md = escape_markdown(ma_don)
    info_md = escape_markdown(thong_tin_don)
    ten_khach_md = escape_markdown(ten_khach)
    slot_md = escape_markdown(slot)
    link_khach_md = escape_markdown(link_khach)

    # Lấy giá bán từ bảng giá
    bang_gia_sheet = connect_to_sheet().worksheet(SHEETS["PRICE"])
    bang_gia_data = bang_gia_sheet.get_all_values()
    gia_int = get_gia_ban(ma_don, product, nguon, bang_gia_data)
    gia_value = "{:,} đ".format(gia_int) if gia_int > 0 else "Chưa xác định"
    gia_md = escape_markdown(str(gia_value))

    # Tạo QR từ VietQR
    try:
        amount = clean_price_to_amount(gia_value)
        qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={ma_don}"
        response = requests.get(qr_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        qr_image = BytesIO(response.content)
    except:
        qr_image = BytesIO()
        Image.new("RGB", (512, 512), "white").save(qr_image, "PNG")

    qr_image.name = "qr.png"
    qr_image.seek(0)

    # Cấu trúc caption
    header = f"📦 Đơn hàng {product_md} với Mã đơn `{ma_don_md}`\n"
    header += f"⛔️ Đã hết hạn {abs(days_left)} ngày trước" if days_left <= 0 else f"⏳ Còn lại {days_left} ngày"

    body = (
        "📦 *THÔNG TIN SẢN PHẨM*\n"
        f"📝 *Mô tả:* {info_md}\n"
        + (f"🧩 *Slot:* {slot_md}\n" if slot else "")
        + (f"📅 Ngày đăng ký: {escape_markdown(ngay_dang_ky)}\n" if ngay_dang_ky else "")
        + f"⏳ *Thời hạn:* {so_ngay} ngày\n"
        + (f"⏳ Ngày hết hạn: {escape_markdown(ngay_het_han)}\n" if ngay_het_han else "")
        + f"💵 *Giá bán:* {gia_md}\n"
        + "\n━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
        + "👤 *THÔNG TIN KHÁCH HÀNG*\n"
        + f"🔸 *Tên:* {ten_khach_md}\n"
        + (f"🔗 *Liên hệ:* {link_khach_md}\n" if link_khach else "")
    )

    footer = (
        escape_markdown("━━━━━━━━━━━━━━━━━━━━━━") + "\n"
        + escape_markdown("💬 Để duy trì dịch vụ liên tục, quý khách nên gia hạn trước ngày hết hạn.") + "\n"
        + escape_markdown("📎 Quý khách vui lòng thanh toán kèm theo mã đơn hàng để dễ dàng đối chiếu.") + "\n"
        + escape_markdown("✨ Trân trọng cảm ơn quý khách!") + "\n\u200b"
    )

    return header + "\n" + escape_markdown("━━━━━━━━━━━━━━━━━━━━━━") + "\n" + body + "\n" + footer, qr_image

# ✅ Thêm xử lý cho nút "Kết thúc" an toàn
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔽 Chọn menu...",
        reply_markup=await show_main_selector(update, context),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def extend_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()

    row_idx = None
    row_data = None
    for i, row in enumerate(data[1:], start=2):  # dòng 2 trở đi
        if row and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            row_idx = i
            row_data = row
            break

    if not row_data:
        await query.edit_message_text("❌ Không tìm thấy đơn hàng cần gia hạn.")
        return

    # ✅ Xác định thời hạn từ tên sản phẩm
    product = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
    matched = re.search(r"--(\d+)m", product)
    if not matched:
        await query.edit_message_text("⚠️ Không xác định được thời hạn từ sản phẩm.")
        return

    so_thang = int(matched.group(1))
    so_ngay = 365 if so_thang == 12 else so_thang * 30

    # ✅ Ngày mới
    ngay_cu = row_data[ORDER_COLUMNS["HET_HAN"]].strip()
    try:
        dt_cu = datetime.strptime(ngay_cu, "%Y-%m-%d")
    except:
        try:
            dt_cu = datetime.strptime(ngay_cu, "%d/%m/%Y")
        except:
            await query.edit_message_text("⚠️ Định dạng ngày hết hạn không hợp lệ.")
            return

    dt_moi = dt_cu + timedelta(days=1)
    ngay_bat_dau = dt_moi.strftime("%d/%m/%Y")
    ngay_het_han = tinh_ngay_het_han(ngay_bat_dau, str(so_ngay))

    # ✅ Cập nhật vào Google Sheet
    sheet.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau)
    sheet.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, str(so_ngay))
    sheet.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han)
    sheet.update_cell(row_idx, ORDER_COLUMNS["CON_LAI"] + 1, f"=I{row_idx}-TODAY()")  # dùng đúng cột I

    # ✅ Cập nhật giá bán/nạp
    bang_gia_sheet = connect_to_sheet().worksheet(SHEETS["PRICE"])
    ds_banggia = bang_gia_sheet.get_all_values()

    sp_don = product.strip().replace("–", "--").replace("—", "--")
    nguon_don = row_data[ORDER_COLUMNS["NGUON"]].strip()
    matched_row = None

    for row in ds_banggia[1:]:
        ten_sp = row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip().replace("–", "--").replace("—", "--")
        nguon = row[PRICE_COLUMNS["NGUON"]].strip()
        if ten_sp == sp_don and nguon == nguon_don:
            matched_row = row
            break

    if matched_row:
        is_ctv = ma_don.upper().startswith("MAVC")
        try:
            gia_nhap_val = clean_price_to_amount(matched_row[PRICE_COLUMNS["GIA_NHAP"]])
            gia_ban_val = clean_price_to_amount(
                matched_row[PRICE_COLUMNS["GIA_BAN_CTV"]] if is_ctv else matched_row[PRICE_COLUMNS["GIA_BAN_LE"]]
            )
        except:
            gia_nhap_val = 0
            gia_ban_val = 0

        sheet.update_cell(row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, gia_nhap_val)
        sheet.update_cell(row_idx, ORDER_COLUMNS["GIA_BAN"] + 1, gia_ban_val)

    # 👉 Điều hướng đơn tiếp theo
    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    keys = list(orders.keys())
    index = context.user_data.get("expired_index", 0)

    if ma_don in orders:
        orders.pop(ma_don)

    if index < len(orders):
        context.user_data["expired_index"] = index
        await show_expired_order(update, context, direction="stay")
    else:
        try:
            await query.message.edit_text("✅ Đã xử lý toàn bộ đơn đến hạn.")
        except:
            pass
        await show_main_selector(update, context)
        context.user_data.pop("expired_orders", None)
        context.user_data.pop("expired_index", None)

async def show_expired_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    index: int = context.user_data.get("expired_index", 0)
    keys = list(orders.keys())

    # ❌ Không còn đơn trong cache
    if not keys:
        await update.callback_query.message.reply_text("✅ Không còn đơn hàng nào.")
        await show_main_selector(update, context)
        return

    # 👉 Điều hướng index
    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1
    index = max(0, min(index, len(keys) - 1))
    context.user_data["expired_index"] = index
    if index >= len(keys):
        await update.callback_query.message.reply_text("✅ Đã xử lý toàn bộ đơn đến hạn.")
        await show_main_selector(update, context)
        context.user_data.pop("expired_orders", None)
        context.user_data.pop("expired_index", None)
        return
    ma_don = keys[index]
    order_info = orders[ma_don]
    row_data = order_info.get("data")
    if not row_data:
        await update.callback_query.message.reply_text("⚠️ Không tìm thấy dữ liệu đơn hàng.")
        return
    caption, qr_image = build_order_caption(row_data)

    # 📌 Tạo nút
    buttons = []
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_expired"))
    if index < len(keys) - 1:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="next_expired"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([
        InlineKeyboardButton("🔄 Gia hạn", callback_data=f"extend_order|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa đơn", callback_data=f"delete_order|{ma_don}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="back_to_menu")
    ])
    reply_markup = InlineKeyboardMarkup(buttons)
    # 📤 Gửi ảnh
    try:
        await update.callback_query.message.edit_media(
            media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="MarkdownV2"),
            reply_markup=reply_markup
        )
    except:
        try:
            await update.callback_query.message.delete()
        except:
            pass

        await update.effective_chat.send_photo(
            photo=qr_image,
            caption=caption,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

    return ConversationHandler.END

async def delete_order_from_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()
    deleted = False

    for i, row in enumerate(data):
        if row and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            sheet.delete_rows(i + 1)
            deleted = True
            break

    if not deleted:
        await query.message.reply_text("❌ Không tìm thấy đơn hàng để xoá.")
        return

    # ✅ Cập nhật cache đơn
    orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
    index = context.user_data.get("expired_index", 0)

    if ma_don in orders:
        orders.pop(ma_don)

    if index >= len(orders):
        index = max(len(orders) - 1, 0)

    context.user_data["expired_index"] = index

    if orders:
        await show_expired_order(update, context, direction="stay")
    else:
        try:
            await query.message.delete()
        except Exception as e:
            print(f"[⚠️ Không thể xoá tin nhắn cũ]: {e}")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ Đã xử lý toàn bộ đơn đến hạn."
        )
        await show_main_selector(update, context)
        context.user_data.pop("expired_orders", None)
        context.user_data.pop("expired_index", None)
    return ConversationHandler.END

# Handlers
prev_expired_handler = CallbackQueryHandler(lambda u, c: show_expired_order(u, c, "prev"), pattern="^prev_expired$")
next_expired_handler = CallbackQueryHandler(lambda u, c: show_expired_order(u, c, "next"), pattern="^next_expired$")
delete_order_handler = CallbackQueryHandler(delete_order_from_expired, pattern=r"^delete_order\||")
extend_order_handler = CallbackQueryHandler(extend_order, pattern=r"^extend_order\||")
