from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from utils import connect_to_sheet
from datetime import datetime
from io import BytesIO
import requests
from PIL import Image
from menu import show_main_selector

def escape_markdown(text):
    special_chars = r'\\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special_chars else c for c in str(text))

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
    nguon_raw = row.get("Nguồn", "")
    days_left = int(float(row.get("Còn Lại", 0)))

    product = escape_markdown(product_raw)
    order_id = escape_markdown(order_id_raw)
    info = escape_markdown(info_raw)
    customer = escape_markdown(customer_raw)

    slot_line = escape_markdown("🎯 Slot: ") + escape_markdown(slot_raw) + "\n" if slot_raw else ""

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
        gia_value = matched_row[4] if is_ctv else matched_row[5]
    else:
        gia_value = row.get("Giá Bán", "")

    if gia_value:
        gia_ban_line += escape_markdown(str(gia_value))
        try:
            clean_value = str(gia_value).replace("đ", "").replace(",", "").replace(" ", "")
            amount = int(float(clean_value))
            qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={order_id_raw}"
        except:
            qr_url = None
    else:
        gia_ban_line += escape_markdown("Chưa xác định")
        qr_url = None

    if days_left <= 0:
        header = f"📦 Đơn hàng {product} với Mã đơn {order_id}\n⛔️ Đã hết hạn {abs(days_left)} ngày Trước"
    else:
        header = f"📦 Đơn hàng {product} với Mã đơn {order_id}\n⏳ Còn lại {days_left} ngày"

    separator = escape_markdown("━━━━━━━━━━━━━━━━━━━━━━")
    body = (
        f"{escape_markdown('📄 Thông tin:')} {info}\n"
        f"{escape_markdown('👤 Khách hàng:')} {customer}\n"
        f"{ngay_dang_ky_line}{ngay_het_han_line}{gia_ban_line}"
    )
    footer = (
        separator + "\n"
        + escape_markdown("💬 Để duy trì dịch vụ liên tục, quý khách nên gia hạn trước ngày hết hạn.") + "\n"
        + escape_markdown("📎 Vui lòng gửi hóa đơn sau khi thanh toán để xác nhận.") + "\n"
        + escape_markdown("✨ Trân trọng cảm ơn quý khách!")
    )

    caption = header + "\n" + separator + "\n" + body + "\n" + footer

    buttons = []
    if index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_expired"))
    buttons.append(InlineKeyboardButton("🔚 Kết thúc", callback_data="back_to_menu"))
    if index < len(orders) - 1:
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data="next_expired"))
    reply_markup = InlineKeyboardMarkup([buttons])

    if qr_url:
        qr_image = BytesIO(requests.get(qr_url).content)
    else:
        img = Image.new("RGB", (512, 512), "white")
        qr_image = BytesIO()
        img.save(qr_image, "PNG")
        qr_image.seek(0)

    qr_image.name = "qr.png"
    await update.callback_query.message.edit_media(
        media=InputMediaPhoto(media=qr_image, caption=caption, parse_mode="MarkdownV2"),
        reply_markup=reply_markup
    )
