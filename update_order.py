# update_order.py
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_main_selector
from add_order import tinh_ngay_het_han
from column import ORDER_COLUMNS

logger = logging.getLogger(__name__)

SELECT_MODE, INPUT_VALUE, SELECT_FIELD, INPUT_NEW_VALUE = range(4)

def chuan_hoa_gia(text):
    try:
        so = int(text.replace(",", "").strip())
        if so < 1000:
            so *= 1000
        return "{:,} đ".format(so), so
    except ValueError:
        return None, None

def get_action_buttons(ma_don):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 Gia Hạn", callback_data=f"extend_order|{ma_don}"),
            InlineKeyboardButton("🗑 Xoá Đơn", callback_data=f"delete_order|{ma_don}")
        ],
        [
            InlineKeyboardButton("🚠 Cập nhật đơn", callback_data="start_edit"),
            InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")
        ]
    ])

def format_order_message(row):
    slot = f"{row[ORDER_COLUMNS['SLOT']]}\n" if row[ORDER_COLUMNS['SLOT']] else ""
    link_khach = row[ORDER_COLUMNS['LINK_KHACH']] if row[ORDER_COLUMNS['LINK_KHACH']] else None
    return (
        f"✅ *CHI TIẾT ĐƠN HÀNG*\n"
        f"📦 Mã đơn: `{escape_markdown(row[ORDER_COLUMNS['ID_DON_HANG']], version=2)}`\n\n"
        f"✧•══════•✧  SẢ̃N PHẨM  ✧•══════•✧\n"
        f"🏷️ *Sản phẩm:* {escape_markdown(row[ORDER_COLUMNS['SAN_PHAM']], version=2)}\n"
        f"📝 *Thông Tin:* {escape_markdown(row[ORDER_COLUMNS['THONG_TIN_DON']], version=2)}\n"
        + (f"🧙 *Slot:* {escape_markdown(slot, version=2)}\n" if slot else "")
        + f"🗓 *Ngày đăng ký:* {escape_markdown(row[ORDER_COLUMNS['NGAY_DANG_KY']], version=2)}\n"
        f"📆 *Số ngày đăng ký:* {escape_markdown(row[ORDER_COLUMNS['SO_NGAY']], version=2)} ngày\n"
        f"⏳ *Hết hạn:* {escape_markdown(row[ORDER_COLUMNS['HET_HAN']], version=2)}\n"
        f"📉 *Còn lại:* {escape_markdown(row[ORDER_COLUMNS['CON_LAI']], version=2)} ngày\n"
        f"🚚 *Nguồn hàng:* {escape_markdown(row[ORDER_COLUMNS['NGUON']], version=2)}\n"
        f"📟 *Giá nhập:* {escape_markdown(row[ORDER_COLUMNS['GIA_NHAP']], version=2)}\n"
        f"💵 *Giá bán:* {escape_markdown(row[ORDER_COLUMNS['GIA_BAN']], version=2)}\n\n"
        f"💰 *Giá trị còn lại:* {escape_markdown(row[ORDER_COLUMNS['GIA_TRI_CON_LAI']], version=2)}\n\n"
        f"✧•══════•✧  KHÁCH HÀNG  ✧•══════•✧\n"
        f"👤 *Tên:* {escape_markdown(row[ORDER_COLUMNS['TEN_KHACH']], version=2)}\n"
        + (f"🔗 *Liên hệ:* {escape_markdown(link_khach, version=2)}\n" if link_khach else "")
    )

async def notify_and_menu(update, context, text: str):
    escaped_text = escape_markdown(text, version=2)
    if update.callback_query:
        await update.callback_query.message.delete()
        chat_id = update.callback_query.message.chat_id
    else:
        await update.message.delete()
        chat_id = update.message.chat_id

    await context.bot.send_message(
        chat_id=chat_id,
        text=escaped_text,
        parse_mode="MarkdownV2"
    )
    await show_main_selector(update, context)

# ❌ KHÔNG escape toàn bộ message ở trong safe_send!
async def safe_send(update, message, markup):
    if update.callback_query:
        await update.callback_query.message.edit_text(
            message,
            parse_mode="MarkdownV2",
            reply_markup=markup
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode="MarkdownV2",
            reply_markup=markup
        )

async def start_update_order(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False) -> int:
    """Bắt đầu quy trình cập nhật đơn hàng, cho chọn hình thức tra cứu."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Mã Đơn", callback_data="check_ma_don"),
            InlineKeyboardButton("📝 Thông Tin SP", callback_data="check_thong_tin")
        ],
        [InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "📋 Vui lòng chọn hình thức kiểm tra:"

    if update.callback_query and edit:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)
    return SELECT_MODE

async def select_check_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý lựa chọn kiểm tra theo Mã Đơn hoặc Thông Tin Sản Phẩm."""
    query = update.callback_query
    await query.answer()

    context.user_data['check_mode'] = query.data
    context.user_data['last_message_id'] = query.message.message_id
    await query.message.edit_reply_markup(reply_markup=None)

    prompt = (
        "🔢 Vui lòng nhập mã đơn hàng:" if query.data == "check_ma_don"
        else "📝 Vui lòng nhập *Thông tin sản phẩm* cần tìm:"
    )

    await query.message.reply_text(
        prompt,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")]
        ]),
        parse_mode="Markdown" if "thong_tin" in query.data else None
    )
    return INPUT_VALUE

async def input_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý giá trị người dùng nhập: Mã Đơn hoặc TTSanPham."""
    text = update.message.text.strip()

    if context.user_data.get("last_message_id"):
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["last_message_id"],
                reply_markup=None
            )
        except:
            pass

    check_mode = context.user_data.get("check_mode")
    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()

    if check_mode == "check_ma_don":
        for idx, row in enumerate(data):
            if row and row[0] == text:
                context.user_data['selected_row'] = idx + 1
                context.user_data['ma_don'] = row[0]
                message = format_order_message(row)
                await safe_send(update, message, get_action_buttons(row[0]))
                return SELECT_FIELD

        await update.message.reply_text("❌ Không tìm thấy mã đơn hàng. Quay về menu chính.")
        return await end_update_success(update, context)

    elif check_mode == "check_thong_tin":
        matched = [
            (idx + 1, row) for idx, row in enumerate(data)
            if len(row) > ORDER_COLUMNS['THONG_TIN_DON'] and text.lower() in row[ORDER_COLUMNS['THONG_TIN_DON']].lower()
        ]

        if not matched:
            await update.message.reply_text("❌ Không tìm thấy đơn hàng nào phù hợp.")
            return await end_update_success(update, context)

        if len(matched) == 1:
            row_idx, row = matched[0]
            context.user_data['selected_row'] = row_idx
            context.user_data['ma_don'] = row[0]
            message = format_order_message(row)
            await safe_send(update, message, get_action_buttons(row[0]))
            return SELECT_FIELD

        context.user_data['matched_orders'] = matched
        context.user_data['matched_index'] = 0
        await update.message.reply_text("⏳ Đang tải đơn hàng đầu tiên...")
        return await show_matched_order(update, context)

async def extend_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gia hạn đơn hàng dựa trên mã đơn và số tháng từ tên sản phẩm."""
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()

    row_idx = None
    row = None
    for i, r in enumerate(data):
        if r and r[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            row_idx = i + 1
            row = r
            break

    if not row:
        return await notify_and_menu(update, context, "❌ Không tìm thấy đơn hàng cần gia hạn.")

    product = row[ORDER_COLUMNS["SAN_PHAM"]]
    match = re.search(r"--(\d+)m", product)
    if not match:
        return await notify_and_menu(update, context, "⚠️ Không xác định được thời hạn từ tên sản phẩm.")

    so_thang = int(match.group(1))
    so_ngay = so_thang * 30

    ngay_cuoi_cu = row[ORDER_COLUMNS["HET_HAN"]].strip()
    if not ngay_cuoi_cu:
        return await notify_and_menu(update, context, "⚠️ Không có ngày hết hạn cũ để tính gia hạn.")

    try:
        start_dt = datetime.strptime(ngay_cuoi_cu, "%d/%m/%Y") + timedelta(days=1)
    except ValueError:
        return await notify_and_menu(update, context, "⚠️ Ngày hết hạn cũ không đúng định dạng.")

    ngay_bat_dau_moi = start_dt.strftime("%d/%m/%Y")
    ngay_het_han_moi = tinh_ngay_het_han(ngay_bat_dau_moi, str(so_ngay))

    sheet.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, str(so_ngay))
    sheet.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau_moi)
    sheet.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi)
    sheet.update_cell(row_idx, ORDER_COLUMNS["CON_LAI"] + 1, f"=I{row_idx}-TODAY()")

    # ✅ Nếu cột Q (index = 16) đang là TRUE thì đổi về FALSE
    if len(row) > 16 and row[16].strip().lower() in ["true", "yes", "1", "x"]:
        sheet.update_cell(row_idx, 17, "FALSE")  # Q là cột thứ 17 (index + 1)

    escaped_ma_don = escape_markdown(ma_don, version=2)
    message = f"✅ Đơn hàng `{escaped_ma_don}` đã được gia hạn thành công\!"
    await safe_send(update, message, markup=None)
    await show_main_selector(update, context)
    return ConversationHandler.END

async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xoá đơn hàng trong Google Sheet theo Mã Đơn."""
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    data = sheet.get_all_values()

    for i, row in enumerate(data):
        if row and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don:
            sheet.delete_rows(i + 1)
            escaped = escape_markdown(ma_don, version=2)
            msg = f"🗑 Đơn hàng `{escaped}` đã được xoá thành công\!"
            await safe_send(update, msg, markup=None)
            await show_main_selector(update, context)
            return ConversationHandler.END

    await notify_and_menu(update, context, "❌ Không tìm thấy đơn hàng để xoá.")
    return ConversationHandler.END

async def show_matched_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str = "stay") -> int:
    """Hiển thị từng đơn hàng khi có nhiều kết quả khớp với Thông Tin Sản Phẩm."""
    matched_orders = context.user_data.get("matched_orders", [])
    index = context.user_data.get("matched_index", 0)

    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1
    index = max(0, min(index, len(matched_orders) - 1))

    context.user_data["matched_index"] = index
    row_idx, row = matched_orders[index]
    context.user_data["selected_row"] = row_idx
    context.user_data["ma_don"] = row[ORDER_COLUMNS["ID_DON_HANG"]]

    message = format_order_message(row)
    buttons = []
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_matched"))
    nav.append(InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel"))
    if index < len(matched_orders) - 1:
        nav.append(InlineKeyboardButton("➡️ Next", callback_data="next_matched"))
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("🔁 Gia Hạn", callback_data=f"extend_order|{row[ORDER_COLUMNS['ID_DON_HANG']]}"),
        InlineKeyboardButton("🗑 Xoá Đơn", callback_data=f"delete_order|{row[ORDER_COLUMNS['ID_DON_HANG']]}")
    ])
    buttons.append([
        InlineKeyboardButton("🛠 Cập nhật đơn", callback_data="start_edit")
    ])

    await safe_send(update, message, InlineKeyboardMarkup(buttons))
    return SELECT_FIELD

async def input_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý giá trị mới nhập để cập nhật nội dung đơn hàng."""
    text = update.message.text.strip()
    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    row_idx = context.user_data.get("selected_row")
    col_idx = context.user_data.get("edit_column")

    if not row_idx or not col_idx:
        await update.message.reply_text("⚠️ Không xác định được dòng cần cập nhật.")
        return await end_update_success(update, context)

    try:
        col_idx_int = int(col_idx)
        if col_idx in [str(ORDER_COLUMNS["GIA_BAN"]), str(ORDER_COLUMNS["GIA_NHAP"])]:
            gia_text, gia_so = chuan_hoa_gia(text)
            if not gia_text:
                await update.message.reply_text("⚠️ Giá không hợp lệ, vui lòng nhập số nguyên.")
                return ConversationHandler.END
            sheet.update_cell(row_idx, col_idx_int + 1, gia_text)

        elif col_idx == str(ORDER_COLUMNS["NGAY_DANG_KY"]):
            # Cập nhật ngày đăng ký và tính lại ngày hết hạn
            sheet.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, text)
            row = sheet.row_values(row_idx)
            so_ngay = row[ORDER_COLUMNS["SO_NGAY"]] if len(row) > ORDER_COLUMNS["SO_NGAY"] else "0"
            if so_ngay:
                try:
                    ngay_het_han = tinh_ngay_het_han(text, so_ngay)
                    sheet.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han)
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Không thể tính ngày hết hạn: {str(e)}")

        else:
            sheet.update_cell(row_idx, col_idx_int + 1, text)

        updated = sheet.row_values(row_idx)
        message = format_order_message(updated)
        await update.message.reply_text(message, parse_mode="MarkdownV2")

    except Exception as e:
        await update.message.reply_text(f"❌ Cập nhật thất bại: {str(e)}")

    return await end_update_success(update, context)

async def start_edit_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hiển thị danh sách các trường để chọn chỉnh sửa đơn hàng."""
    keyboard = [
        [
            InlineKeyboardButton("📌 Sản phẩm", callback_data="edit_col_1"),
            InlineKeyboardButton("📝 Chi tiết", callback_data="edit_col_2"),
            InlineKeyboardButton("📆 Ngày Đăng Ký", callback_data="edit_ngay_dang_ky")
        ],
        [
            InlineKeyboardButton("🎯 Slot", callback_data="edit_col_5"),
            InlineKeyboardButton("📅 Số Ngày Đăng Ký", callback_data="edit_col_7"),
            InlineKeyboardButton("🚚 Nguồn Cấp Hàng", callback_data="edit_col_10")
        ],
        [
            InlineKeyboardButton("🧾 Giá Nhập", callback_data="edit_col_11"),
            InlineKeyboardButton("💵 Giá Bán", callback_data="edit_col_12"),
            InlineKeyboardButton("👤 Tên Khách Hàng", callback_data="edit_col_3")
        ],
        [
            InlineKeyboardButton("🔗 Link Khách", callback_data="edit_col_4"),
            InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")
        ]
    ]
    await update.callback_query.answer()
    await update.callback_query.message.edit_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text(
        "📋 Vui lòng chọn nội dung cần chỉnh sửa:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_FIELD
async def edit_ngay_dang_ky_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu nhập ngày đăng ký mới để cập nhật đơn hàng."""
    query = update.callback_query
    await query.answer()
    context.user_data['edit_column'] = str(ORDER_COLUMNS['NGAY_DANG_KY'])  # "6"
    context.user_data["last_message_id"] = query.message.message_id

    await query.message.edit_reply_markup(reply_markup=None)
    await query.message.reply_text("📅 Vui lòng nhập *Ngày đăng ký mới* (dd/mm/yyyy):", parse_mode="Markdown")
    return INPUT_NEW_VALUE

async def choose_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng chọn cột cần chỉnh sửa."""
    query = update.callback_query
    await query.answer()
    context.user_data['edit_column'] = query.data.split("_")[-1]
    await query.message.edit_reply_markup(reply_markup=None)
    msg = await query.message.reply_text("✏️ Vui lòng nhập nội dung cần chỉnh sửa:")
    context.user_data["last_message_id"] = msg.message_id
    return INPUT_NEW_VALUE

async def end_update_with_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng hủy cập nhật đơn hàng."""
    try:
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.message.edit_text("❌ Đã hủy cập nhật đơn.")
            except Exception as e:
                logger.warning(f"[❌ Không thể sửa tin nhắn cũ]: {e}")
        elif update.message:
            await update.message.reply_text("❌ Đã hủy cập nhật đơn.")
    finally:
        await show_main_selector(update, context, edit=False)

    return ConversationHandler.END

async def end_update_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Quay về menu chính khi cập nhật thành công hoặc kết thúc hợp lệ."""
    await show_main_selector(update, context)
    return ConversationHandler.END

def get_update_order_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("update", start_update_order),
            CallbackQueryHandler(lambda u, c: start_update_order(u, c, edit=True), pattern="^update$")
        ],
        states={
            SELECT_MODE: [
                CallbackQueryHandler(select_check_mode, pattern="^check_ma_don$"),
                CallbackQueryHandler(select_check_mode, pattern="^check_thong_tin$")
            ],
            INPUT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_value_handler)
            ],
            SELECT_FIELD: [
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "prev"), pattern="^prev_matched$"),
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "next"), pattern="^next_matched$"),
                CallbackQueryHandler(start_edit_update, pattern="^start_edit$"),
                CallbackQueryHandler(choose_field_to_edit, pattern="^edit_col_.*"),
                CallbackQueryHandler(extend_order, pattern="^extend_order\\|"),
                CallbackQueryHandler(delete_order, pattern="^delete_order\\|"),
                CallbackQueryHandler(edit_ngay_dang_ky_handler, pattern="^edit_ngay_dang_ky$")

            ],
            INPUT_NEW_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_value_handler)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(end_update_with_cancel, pattern="^end_update_with_cancel$"),
            CommandHandler("cancel", end_update_with_cancel)
        ],
        name="update_order_conversation",
        persistent=False
    )
