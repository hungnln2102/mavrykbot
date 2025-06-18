from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_outer_menu
from collections import OrderedDict


def extract_unpaid_orders():
    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_records()
    orders_dict = OrderedDict()

    for row in data:
        days_left = row.get("Còn Lại", 0)
        check = str(row.get("Check", "")).strip()
        ma_don = row.get("ID Đơn Hàng", "")

        if not ma_don or check != "":
            continue

        if isinstance(days_left, (int, float)) and days_left > 4:
            orders_dict[ma_don] = {"data": row}

    return orders_dict


def build_order_text(data):
    def safe(text): return escape_markdown(str(text), version=1)

    ma_san_pham = safe(data.get("Sản Phẩm", ""))
    mo_ta = safe(data.get("Thông tin sản phẩm", ""))
    slot = safe(data.get("Slot", ""))
    ngay_bat_dau = safe(data.get("Ngày Đăng Ký", ""))
    so_ngay = safe(data.get("Số Ngày Đã Đăng Ký", ""))
    ngay_het_han_md = safe(data.get("Hết Hạn", ""))
    gia_ban = safe(data.get("Giá Bán", ""))
    khach_hang = safe(data.get("Khách hàng", ""))
    link_khach = safe(data.get("Link Khách", ""))

    text = (
        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"🔸 *Tên:* {ma_san_pham}\n"
        f"📄 *Thông Tin Đơn Hàng:* {mo_ta}\n"
        + (f"🔢 *Slot:* {slot}\n" if slot else "")
        + f"📅 *Ngày Bắt đầu:* {ngay_bat_dau}\n"
        + f"⏳ *Thời hạn:* {so_ngay} ngày\n"
        + f"📆 *Ngày Hết hạn:* {ngay_het_han_md}\n"
        + f"💵 *Giá bán:* {gia_ban}\n"
        + "\n🧍‍♂️ ─── 👤 ─── 🧍‍♀️\n\n"
        + f"📌 *THÔNG TIN KHÁCH HÀNG*\n"
        + f"👤 *Tên Khách Hàng:* {khach_hang}\n"
        + (f"🔗 *Thông Tin Liên hệ:* {link_khach}\n" if link_khach else "")
    )
    return text


async def view_unpaid_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = extract_unpaid_orders()

    if not orders:
        await update.callback_query.message.reply_text("✅ Hiện không có đơn hàng nào chưa thanh toán.")
        await show_outer_menu(update, context)
        return ConversationHandler.END

    context.user_data["unpaid_orders"] = orders
    context.user_data["unpaid_index"] = 0
    await show_unpaid_order(update, context, direction="stay")


async def show_unpaid_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    orders = context.user_data.get("unpaid_orders", OrderedDict())
    index = context.user_data.get("unpaid_index", 0)
    keys = list(orders.keys())

    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1

    if index < 0:
        index = 0
    if index >= len(keys):
        msg_id = context.user_data.get("last_order_msg_id")
        try:
            if msg_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except:
            pass

        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Đã xử lý toàn bộ đơn chưa thanh toán.")
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data["unpaid_index"] = index
    ma_don = keys[index]
    data = orders[ma_don]["data"]
    text = build_order_text(data)

    buttons = []
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_unpaid"))
    if index < len(keys) - 1:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="next_unpaid"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("✅ Đã Thanh Toán", callback_data=f"paid_unpaid|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa đơn", callback_data=f"delete_unpaid|{ma_don}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="exit_unpaid")
    ])

    reply_markup = InlineKeyboardMarkup(buttons)
    msg = await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    context.user_data["last_order_msg_id"] = msg.message_id


async def delete_unpaid_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1]

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()
    for i, row in enumerate(data):
        if row and row[0].strip() == ma_don.strip():
            sheet.delete_rows(i + 1)
            break

    orders: OrderedDict = context.user_data.get("unpaid_orders", OrderedDict())
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
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
        except:
            pass

        await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Đã xử lý toàn bộ đơn chưa thanh toán.")
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END


async def mark_paid_unpaid_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1]

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()
    for i, row in enumerate(data):
        if row and row[0].strip() == ma_don.strip():
            sheet.update_cell(i + 1, 17, True)
            break

    orders: OrderedDict = context.user_data.get("unpaid_orders", OrderedDict())
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
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
        except:
            pass

        await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Đã xử lý toàn bộ đơn chưa thanh toán.")
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END


async def exit_unpaid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        msg_id = context.user_data.get("last_order_msg_id")
        if msg_id:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
    except:
        pass

    await context.bot.send_message(chat_id=query.message.chat_id, text="🔚 Đã thoát khỏi phiên làm việc.")
    await show_outer_menu(update, context)
    context.user_data.clear()
    return ConversationHandler.END
