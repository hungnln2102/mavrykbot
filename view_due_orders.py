import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.helpers import escape_markdown as tg_escape_md
from utils import connect_to_sheet
from add_order import tinh_ngay_het_han
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from menu import show_main_selector

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
    test_sheet = spreadsheet.worksheet("Bảng Đơn Hàng")
    data = test_sheet.get_all_records()

    orders = []
    for row in data:
        days_left = row.get("Còn Lại")
        if isinstance(days_left, (int, float)) and days_left <= 4:
            orders.append(row)

    if not orders:
        await update.callback_query.message.reply_text(
            escape_markdown("✅ Hiện không có đơn hàng nào sắp hết hạn."),
            parse_mode="MarkdownV2"
        )
        await show_main_selector(update, context)
        return

    context.user_data["expired_orders"] = orders
    context.user_data["expired_index"] = 0

    await show_expired_order(update, context, direction="stay")

async def view_expired_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    spreadsheet = connect_to_sheet()
    test_sheet = spreadsheet.worksheet("Bảng Đơn Hàng")
    data = test_sheet.get_all_records()

    orders = []
    for row in data:
        days_left = row.get("Còn Lại")
        if isinstance(days_left, (int, float)) and days_left <= 4:
            orders.append(row)

    if not orders:
        await update.callback_query.message.reply_text(
            escape_markdown("✅ Hiện không có đơn hàng nào sắp hết hạn."),
            parse_mode="MarkdownV2"
        )
        await show_main_selector(update, context)
        return

    context.user_data["expired_orders"] = orders
    context.user_data["expired_index"] = 0

    await show_expired_order(update, context, direction="stay")

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
    so_ngay = so_thang * 30

    # 📅 Tính ngày bắt đầu và hết hạn mới
    ngay_ket_thuc_cu = row_data.get("Hết Hạn", "")
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
        ten_sp = row_bang_gia[0].strip().replace("–", "-").replace("—", "-")
        nguon = row_bang_gia[2].strip()
        sp_don = product.strip().replace("–", "-").replace("—", "-")
        nguon_don = row_data.get("Nguồn", "").strip()
        if ten_sp == sp_don and nguon == nguon_don:
            matched_row = row_bang_gia
            break

    if matched_row:
        is_ctv = ma_don.upper().startswith("MAVC")
        gia_nhap = matched_row[3]
        gia_ban = matched_row[4] if is_ctv else matched_row[5]
        sheet.update_cell(row_idx, 12, gia_nhap)  # L
        sheet.update_cell(row_idx, 13, gia_ban)   # M

    # 📨 Gửi thông báo thành công
    msg = f"✅ Đơn hàng `{tg_escape_md(ma_don, version=2)}` đã được *gia hạn {so_thang} tháng* thành công\\!"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg,
        parse_mode="MarkdownV2"
    )

    # 🔚 Quay về menu chính
    await show_main_selector(update, context)

async def show_expired_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    spreadsheet = connect_to_sheet()
    test_sheet = spreadsheet.worksheet("Bảng Đơn Hàng")
    bang_gia_sheet = spreadsheet.worksheet("Bảng Giá")
    bang_gia_data = bang_gia_sheet.get_all_values()
    orders = context.user_data.get("expired_orders", [])
    index = context.user_data.get("expired_index", 0)

    if not orders:
        await update.callback_query.message.reply_text("❌ Không còn đơn hàng nào.")
        return

    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1

    if index < 0 or index >= len(orders):
        await update.callback_query.message.reply_text("❌ Không có đơn hàng nào tại vị trí này.")
        return

    context.user_data["expired_index"] = index
    row = orders[index]

    product_raw = row.get("Sản Phẩm", "")
    order_id_raw = row.get("ID Đơn Hàng", "")
    info_raw = row.get("Thông tin sản phẩm", "")
    customer_raw = row.get("Khách hàng", "")
    slot_raw = row.get("Slot", "")
    ngay_dang_ky_raw = row.get("Ngày Đăng Ký", "")
    ngay_het_han_raw = row.get("Hết Hạn", "")
    days_left = int(float(row.get("Còn Lại", 0)))

    product = escape_markdown(product_raw)
    order_id = escape_markdown(order_id_raw)
    info = escape_markdown(info_raw)
    customer = escape_markdown(customer_raw)

    ngay_dang_ky_line = ""
    if ngay_dang_ky_raw:
        try:
            parsed = datetime.strptime(str(ngay_dang_ky_raw), "%Y-%m-%d")
            formatted = parsed.strftime("%d/%m/%Y")
            ngay_dang_ky_line = escape_markdown("📅 Ngày đăng ký: ") + escape_markdown(formatted) + "\n"
        except:
            ngay_dang_ky_line = escape_markdown("📅 Ngày đăng ký: ") + escape_markdown(str(ngay_dang_ky_raw)) + "\n"

    ngay_het_han_line = ""
    if ngay_het_han_raw:
        try:
            parsed = datetime.strptime(str(ngay_het_han_raw), "%Y-%m-%d")
            formatted = parsed.strftime("%d/%m/%Y")
            ngay_het_han_line = escape_markdown("⏳ Ngày hết hạn: ") + escape_markdown(formatted) + "\n"
        except:
            ngay_het_han_line = escape_markdown("⏳ Ngày hết hạn: ") + escape_markdown(str(ngay_het_han_raw)) + "\n"

    gia_ban_line = escape_markdown("💰 Giá tiền: ")
    matched_row = None
    for row_bang_gia in bang_gia_data[1:]:
        ten_sp = row_bang_gia[0].strip().replace("–", "-").replace("—", "-")
        nguon = row_bang_gia[2].strip()
        sp_don = row.get("Sản Phẩm", "").strip().replace("–", "-").replace("—", "-")
        nguon_don = row.get("Nguồn", "").strip()
        if ten_sp == sp_don and nguon == nguon_don:
            matched_row = row_bang_gia
            break

    if matched_row:
        is_ctv = order_id_raw.upper().startswith("MAVC")
        gia_ban = matched_row[4] if is_ctv else matched_row[5]
        gia_value = gia_ban
    else:
        gia_value = row.get("Giá Bán", "")

    if gia_value:
        gia_ban_line += escape_markdown(str(gia_value))
        try:
            amount = clean_price_to_amount(str(gia_value))
            qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={order_id_raw}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(qr_url, headers=headers)
            qr_image = BytesIO(response.content)
            qr_image.name = "qr.png"
            qr_image.seek(0)
        except:
            img = Image.new("RGB", (512, 512), "white")
            qr_image = BytesIO()
            img.save(qr_image, "PNG")
            qr_image.name = "qr.png"
            qr_image.seek(0)
    else:
        gia_ban_line += escape_markdown("Chưa xác định")
        img = Image.new("RGB", (512, 512), "white")
        qr_image = BytesIO()
        img.save(qr_image, "PNG")
        qr_image.name = "qr.png"
        qr_image.seek(0)

    if days_left <= 0:
        header = f"📦 Đơn hàng {product} với Mã đơn {order_id}\n⛔️ Đã hết hạn {abs(days_left)} ngày Trước"
    else:
        header = f"📦 Đơn hàng {product} với Mã đơn {order_id}\n⏳ Còn lại {days_left} ngày"

    separator = escape_markdown("━━━━━━━━━━━━━━━━━━━━━━")
    body = (
    f"📦 *THÔNG TIN SẢN PHẨM*\n"
    f"📝 *Mô tả:* {info}\n"
    + (f"🧩 *Slot:* {slot_raw}\n" if slot_raw else "")
    + ngay_dang_ky_line
    + f"⏳ *Thời hạn:* {row.get('Số Ngày', '')} ngày\n"
    + ngay_het_han_line
    + f"💵 *Giá bán:* {gia_value}\n"
    + "\n━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
    + f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
    + f"🔸 *Tên:* {customer}\n"
    + (f"🔗 *Liên hệ:* {row.get('Link Khách', '')}\n" if row.get('Link Khách') else "")
)
    footer = (
        separator + "\n"
        + escape_markdown("💬 Để duy trì dịch vụ liên tục, quý khách nên gia hạn trước ngày hết hạn.") + "\n"
        + escape_markdown("📎 Quý Khách vui lòng thanh toán kèm theo mã đơn hàng để dễ dàng đối chiếu.") + "\n"
        + escape_markdown("✨ Trân trọng cảm ơn quý khách!")
    )

    caption = header + "\n" + separator + "\n" + body + "\n" + footer + "\n\u200b"

    buttons = []

# Dòng điều hướng
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_expired"))
    if index < len(orders) - 1:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="next_expired"))
    if nav_row:
        buttons.append(nav_row)

    # Dòng chức năng chính
    buttons.append([
        InlineKeyboardButton("🔄 Gia hạn", callback_data=f"extend_order|{order_id_raw}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="back_to_menu")
    ])
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.callback_query.message.edit_media(
    media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="MarkdownV2"),
    reply_markup=reply_markup
)


# Thêm vào list handler trong function setup hoặc return ConversationHandler
extend_order_handler = CallbackQueryHandler(extend_order, pattern=r"^extend_order\|")