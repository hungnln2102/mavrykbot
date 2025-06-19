import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler
from telegram.helpers import escape_markdown as tg_escape_md
from utils import connect_to_sheet
from add_order import tinh_ngay_het_han
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from menu import show_main_selector
from collections import OrderedDict


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
    spreadsheet = connect_to_sheet()
    sheet = spreadsheet.worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_records()

    orders_dict = OrderedDict()
    for row in data:
        days_left = row.get("Còn Lại")
        ma_don = row.get("ID Đơn Hàng", "")
        if isinstance(days_left, (int, float)) and days_left <= 4 and ma_don:
            orders_dict[ma_don] = {"data": row}

    if not orders_dict:
        await update.callback_query.message.reply_text(
            escape_markdown("✅ Hiện không có đơn hàng nào sắp hết hạn."),
            parse_mode="MarkdownV2"
        )
        await show_main_selector(update, context)
        return ConversationHandler.END

    context.user_data["expired_orders"] = orders_dict
    context.user_data["expired_index"] = 0
    await show_expired_order(update, context, direction="stay")
    
def get_gia_ban(ma_don, ma_san_pham, nguon, ds_banggia):
    sp_don = ma_san_pham.strip().replace("–", "--").replace("—", "--")
    nguon_don = nguon.strip()

    for row in ds_banggia:
        if len(row) < 6:
            continue
        sp_goc = row[0].strip().replace("–", "--").replace("—", "--")
        nguon_goc = row[2].strip()

        if sp_goc == sp_don and nguon_goc == nguon_don:
            try:
                gia_str = row[4] if ma_don.upper().startswith("MAVC") else row[5]
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
            except:
                return 0
    return 0

def build_order_caption(data):
    product_raw = data.get("Sản Phẩm", "")
    order_id_raw = data.get("ID Đơn Hàng", "")
    info_raw = data.get("Thông tin sản phẩm", "")
    customer_raw = data.get("Khách hàng", "")
    slot_raw = data.get("Slot", "")
    ngay_dang_ky_raw = data.get("Ngày Đăng Ký", "")
    ngay_het_han_raw = data.get("Hết Hạn", "")
    so_ngay = data.get("Số Ngày Đã Đăng Ký", "")
    days_left = int(float(data.get("Còn Lại", 0)))

    product = escape_markdown(product_raw)
    order_id = escape_markdown(order_id_raw)
    info = escape_markdown(info_raw)
    customer = escape_markdown(customer_raw)

    ngay_dang_ky_line = f"📅 Ngày đăng ký: {escape_markdown(ngay_dang_ky_raw)}\n" if ngay_dang_ky_raw else ""
    ngay_het_han_line = f"⏳ Ngày hết hạn: {escape_markdown(ngay_het_han_raw)}\n" if ngay_het_han_raw else ""

    spreadsheet = connect_to_sheet()
    bang_gia_sheet = spreadsheet.worksheet("Bảng Giá")
    bang_gia_data = bang_gia_sheet.get_all_values()

    ma_san_pham = data.get("Sản Phẩm", "")
    nguon = data.get("Nguồn", "")
    ma_don = data.get("ID Đơn Hàng", "")
    gia_int = get_gia_ban(ma_don, ma_san_pham, nguon, bang_gia_data)
    gia_value = "{:,} đ".format(gia_int) if gia_int > 0 else "Chưa xác định"

    try:
        amount = clean_price_to_amount(str(gia_value))
        qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={order_id_raw}"
        response = requests.get(qr_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        qr_image = BytesIO(response.content)
    except:
        qr_image = BytesIO()
        Image.new("RGB", (512, 512), "white").save(qr_image, "PNG")

    qr_image.name = "qr.png"
    qr_image.seek(0)

    header = f"📦 Đơn hàng {product} với Mã đơn `{order_id}`\n"
    header += f"⛔️ Đã hết hạn {abs(days_left)} ngày trước" if days_left <= 0 else f"⏳ Còn lại {days_left} ngày"

    body = (
        "📦 *THÔNG TIN SẢN PHẨM*\n"
        + f"📝 *Mô tả:* {info}\n"
        + (f"🧩 *Slot:* {escape_markdown(slot_raw)}\n" if slot_raw else "")
        + ngay_dang_ky_line
        + f"⏳ *Thời hạn:* {so_ngay} ngày\n"
        + ngay_het_han_line
        + f"💵 *Giá bán:* {escape_markdown(str(gia_value))}\n"
        + "\n━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
        + f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        + f"🔸 *Tên:* {customer}\n"
        + (f"🔗 *Liên hệ:* {escape_markdown(data.get('Link Khách', ''))}\n" if data.get('Link Khách') else "")
    )

    footer = (
        escape_markdown("━━━━━━━━━━━━━━━━━━━━━━") + "\n"
        + escape_markdown("💬 Để duy trì dịch vụ liên tục, quý khách nên gia hạn trước ngày hết hạn.") + "\n"
        + escape_markdown("📎 Quý Khách vui lòng thanh toán kèm theo mã đơn hàng để dễ dàng đối chiếu.") + "\n"
        + escape_markdown("✨ Trân trọng cảm ơn quý khách!") + "\n\u200b"
    )

    return header + "\n" + escape_markdown("━━━━━━━━━━━━━━━━━━━━━━") + "\n" + body + "\n" + footer, qr_image

async def extend_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1]

    spreadsheet = connect_to_sheet()
    sheet = spreadsheet.worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_records()

    row_idx = None
    row_data = None
    for i, row in enumerate(data, start=2):  # Bỏ dòng tiêu đề
        if str(row.get("ID Đơn Hàng", "")).strip() == ma_don:
            row_idx = i
            row_data = row
            break

    if not row_data:
        await query.edit_message_text("❌ Không tìm thấy đơn hàng cần gia hạn.")
        return

    # 📦 Xác định thời hạn từ tên sản phẩm (ví dụ: "Edifier --2m")
    product = row_data.get("Sản Phẩm", "")
    matched = re.search(r"--(\d+)m", product)
    if not matched:
        await query.edit_message_text("⚠️ Không xác định được thời hạn từ sản phẩm.")
        return

    so_thang = int(matched.group(1))
    if so_thang == 12:
        so_ngay = 365
    else:
        so_ngay = so_thang * 30

    # 📅 Tính ngày bắt đầu và hết hạn mới
    ngay_ket_thuc_cu = row_data.get("Ngày Hết Hạn", "")
    try:
        dt_ket_thuc = datetime.strptime(str(ngay_ket_thuc_cu), "%Y-%m-%d")
    except:
        try:
            dt_ket_thuc = datetime.strptime(str(ngay_ket_thuc_cu), "%d/%m/%Y")
        except:
            await query.edit_message_text("⚠️ Định dạng ngày hết hạn không hợp lệ.")
            return

    dt_bat_dau_moi = dt_ket_thuc + timedelta(days=1)
    ngay_bat_dau_str = dt_bat_dau_moi.strftime("%d/%m/%Y")
    ngay_ket_thuc_str = tinh_ngay_het_han(ngay_bat_dau_str, str(so_ngay))

    # ✅ Cập nhật ngày và thời hạn
    sheet.update_cell(row_idx, 7, ngay_bat_dau_str)     # G
    sheet.update_cell(row_idx, 8, str(so_ngay))         # H
    sheet.update_cell(row_idx, 9, ngay_ket_thuc_str)    # I
    sheet.update_cell(row_idx, 10, f"=I{row_idx}-TODAY()")  # J

    # 🔁 Cập nhật giá theo bảng giá nếu có khớp
    bang_gia_sheet = spreadsheet.worksheet("Bảng Giá")
    bang_gia_data = bang_gia_sheet.get_all_values()

    matched_row = None
    for row_bang_gia in bang_gia_data[1:]:
        ten_sp = row_bang_gia[0].strip().replace("–", "--").replace("—", "--")
        nguon = row_bang_gia[2].strip()
        sp_don = product.strip().replace("–", "--").replace("—", "--")
        nguon_don = row_data.get("Nguồn", "").strip()
        if ten_sp == sp_don and nguon == nguon_don:
            matched_row = row_bang_gia
            break

    if matched_row:
        is_ctv = ma_don.upper().startswith("MAVC")
        def parse_gia(gia_str):
            return int(str(gia_str).strip().replace(",", "").replace("₫", "").replace(" đ", "").replace(".", ""))

    try:
        gia_nhap_val = parse_gia(matched_row[3])
        gia_ban_val = parse_gia(matched_row[4] if is_ctv else matched_row[5])
    except:
        gia_nhap_val = 0
        gia_ban_val = 0

    sheet.update_cell(row_idx, 12, gia_nhap_val)  # L
    sheet.update_cell(row_idx, 13, gia_ban_val)   # M


    # 👉 Nếu gọi từ luồng đơn đến hạn → chuyển tiếp đơn tiếp theo
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

    # 👉 Điều hướng
    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1

    # 👉 Chốt index
    if index < 0:
        index = 0
    if index >= len(keys):
        await update.callback_query.message.reply_text("✅ Đã xử lý toàn bộ đơn đến hạn.")
        await show_main_selector(update, context)
        context.user_data.pop("expired_orders", None)
        context.user_data.pop("expired_index", None)
        return

    context.user_data["expired_index"] = index
    ma_don = keys[index]
    order_info = orders[ma_don]
    data = order_info.get("data", {})
    caption, qr_image = build_order_caption(data)

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
    ma_don = query.data.split("|")[1]

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()
    deleted = False

    for i, row in enumerate(data):
        if row and row[0].strip() == ma_don.strip():
            sheet.delete_rows(i + 1)
            deleted = True
            break

    if deleted:
    # ✅ Xoá mã đơn khỏi cache
        orders: OrderedDict = context.user_data.get("expired_orders", OrderedDict())
        index = context.user_data.get("expired_index", 0)
        keys = list(orders.keys())

    if ma_don in orders:
        orders.pop(ma_don)

    if index >= len(orders):
        index = max(len(orders) - 1, 0)

    context.user_data["expired_index"] = index

    if orders:
        await show_expired_order(update, context, direction="stay")
    else:
        try:
            await query.message.delete()  # ✅ Xoá ảnh/QR hoặc tin nhắn cũ
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
