from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_outer_menu
from collections import OrderedDict
from column import SHEETS, ORDER_COLUMNS


def extract_unpaid_orders():
    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()
    orders_dict = OrderedDict()

    for row in data[1:]:  # Bỏ header
        try:
            ma_don = row[ORDER_COLUMNS["ID_DON_HANG"]].strip()
            check = str(row[ORDER_COLUMNS["CHECK"]]).strip()
            days_left_raw = row[ORDER_COLUMNS["CON_LAI"]]
            days_left = float(days_left_raw) if str(days_left_raw).replace(".", "", 1).isdigit() else 0
        except (IndexError, ValueError):
            continue
        if not ma_don or check != "":
            continue
        if days_left > 4:
            orders_dict[ma_don] = {"data": row}

    return orders_dict

def build_order_text(row):
    def safe(val): return escape_markdown(str(val or ""), version=1)

    ten_san_pham = safe(row[ORDER_COLUMNS["SAN_PHAM"]])
    thong_tin_don = safe(row[ORDER_COLUMNS["THONG_TIN_DON"]])
    slot = safe(row[ORDER_COLUMNS["SLOT"]])
    ngay_bat_dau = safe(row[ORDER_COLUMNS["NGAY_DANG_KY"]])
    so_ngay = safe(row[ORDER_COLUMNS["SO_NGAY"]])
    ngay_het_han = safe(row[ORDER_COLUMNS["HET_HAN"]])
    gia_ban = safe(row[ORDER_COLUMNS["GIA_BAN"]])
    ten_khach = safe(row[ORDER_COLUMNS["TEN_KHACH"]])
    link_khach = safe(row[ORDER_COLUMNS["LINK_KHACH"]])

    text = (
        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"🔸 *Tên:* {ten_san_pham}\n"
        f"📄 *Thông Tin Đơn Hàng:* {thong_tin_don}\n"
        + (f"🔢 *Slot:* {slot}\n" if slot else "")
        + f"📅 *Ngày Bắt đầu:* {ngay_bat_dau}\n"
        + f"⏳ *Thời hạn:* {so_ngay} ngày\n"
        + f"📆 *Ngày Hết hạn:* {ngay_het_han}\n"
        + f"💵 *Giá bán:* {gia_ban}\n"
        + "\n🧍‍♂️ ─── 👤 ─── 🧍‍♀️\n\n"
        + f"📌 *THÔNG TIN KHÁCH HÀNG*\n"
        + f"👤 *Tên Khách Hàng:* {ten_khach}\n"
        + (f"🔗 *Thông Tin Liên hệ:* {link_khach}\n" if link_khach else "")
    )

    return text

async def view_unpaid_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = extract_unpaid_orders()

    if not orders:
        try:
            if update.callback_query:
                await update.callback_query.message.delete()
            elif update.message:
                await update.message.delete()
        except:
            pass

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Hiện không có đơn hàng nào chưa thanh toán."
        )
        await show_outer_menu(update, context)
        return ConversationHandler.END

    # Ghi dữ liệu vào context
    context.user_data["unpaid_orders"] = orders
    context.user_data["unpaid_index"] = 0
    await show_unpaid_order(update, context, direction="stay")

async def show_unpaid_order(update, context, direction: str):
    orders = context.user_data.get("unpaid_orders", OrderedDict())
    index = context.user_data.get("unpaid_index", 0)
    keys = list(orders.keys())

    # Điều hướng index
    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1

    # Kiểm tra giới hạn
    if index < 0:
        index = 0
    if index >= len(keys):
        try:
            msg_id = context.user_data.get("last_order_msg_id")
            if msg_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except:
            pass

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Đã xử lý toàn bộ đơn chưa thanh toán."
        )
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    # Gán index mới
    context.user_data["unpaid_index"] = index
    ma_don = keys[index]
    row_data = orders[ma_don]["data"]
    text = build_order_text(row_data)

    # ===== Nút điều hướng =====
    buttons = []
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_unpaid"))
    if index < len(keys) - 1:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="next_unpaid"))
    if nav_row:
        buttons.append(nav_row)

    # ===== Nút thao tác =====
    buttons.append([
        InlineKeyboardButton("✅ Đã Thanh Toán", callback_data=f"paid_unpaid|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa đơn", callback_data=f"delete_unpaid|{ma_don}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="exit_unpaid"),
    ])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Gửi lại tin nhắn
    msg = await update.callback_query.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    context.user_data["last_order_msg_id"] = msg.message_id


def update_context_after_action(context, ma_don):
    orders = context.user_data.get("unpaid_orders", OrderedDict())
    index = context.user_data.get("unpaid_index", 0)
    if ma_don in orders:
        orders.pop(ma_don)
    if index >= len(orders):
        index = max(len(orders) - 1, 0)
    context.user_data["unpaid_index"] = index
    return orders

async def delete_unpaid_order(update, context):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()
    for i, row in enumerate(data):
        if row and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            sheet.delete_rows(i + 1)
            break
    await update_unpaid_context_after_action(update, context, ma_don)

async def mark_paid_unpaid_order(update, context):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
    data = sheet.get_all_values()
    for i, row in enumerate(data):
        if row and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            sheet.update_cell(i + 1, ORDER_COLUMNS["CHECK"] + 1, "False")
            break
    await update_unpaid_context_after_action(update, context, ma_don)

async def exit_unpaid(update, context):
    query = update.callback_query
    await query.answer()

    # Xoá message đơn hàng nếu có
    try:
        msg_id = context.user_data.get("last_order_msg_id")
        if msg_id:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
    except Exception as e:
        print(f"[⚠️ Không thể xoá message]: {e}")
    await context.bot.send_message(chat_id=query.message.chat_id, text="🔚 Đã thoát khỏi phiên làm việc.")
    await show_outer_menu(update, context)
    context.user_data.clear()
    return ConversationHandler.END

async def update_unpaid_context_after_action(update, context, ma_don):
    orders = context.user_data.get("unpaid_orders", OrderedDict())
    index = context.user_data.get("unpaid_index", 0)

    if ma_don in orders:
        orders.pop(ma_don)
    if index >= len(orders):
        index = max(len(orders) - 1, 0)
    context.user_data["unpaid_index"] = index

    if orders:
        await show_unpaid_order(update, context, direction="stay")
    else:
        try:
            msg_id = context.user_data.get("last_order_msg_id")
            if msg_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except:
            pass
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Đã xử lý toàn bộ đơn chưa thanh toán."
        )
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END
