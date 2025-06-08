# update_order.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_main_selector
from add_order import tinh_ngay_het_han

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

def format_order_message(row):
    slot = f"🎯 Slot: {row[5]}\n" if len(row) > 5 and row[5] else ""
    link_khach = row[4] if len(row) > 4 and row[4] else None
    message = (
        f"✅ *CHI TIẾT ĐƠN HÀNG*\n"
        f"📦 Mã đơn: `{escape_markdown(row[0], version=2)}`\n\n"

        f"✧═════• ༺ 𝐓𝐇𝐎̂𝐍𝐆 𝐓𝐈𝐍 𝐒𝐀̉𝐍 𝐏𝐇𝐀̂̉𝐌 ༻ •═════✧\n"
        f"🏷️ *Sản phẩm:* {escape_markdown(row[1], version=2)}\n"
        f"📝 *Chi tiết:* {escape_markdown(row[2], version=2)}\n"
        + (f"🧩 *Slot:* {escape_markdown(slot, version=2)}\n" if slot else "")
        + f"📅 *Ngày đăng ký:* {escape_markdown(row[6], version=2)}\n"
        f"📆 *Số ngày đăng ký:* {escape_markdown(row[7], version=2)} ngày\n"
        f"⏳ *Hết hạn:* {escape_markdown(row[8], version=2)}\n"
        f"📉 *Còn lại:* {escape_markdown(row[9], version=2)} ngày\n"
        f"🚚 *Nguồn hàng:* {escape_markdown(row[10], version=2)}\n"
        f"🧾 *Giá nhập:* {escape_markdown(row[11], version=2)}\n"
        f"💵 *Giá bán:* {escape_markdown(row[12], version=2)}\n\n"

        f"✧═════• ༺ 𝐓𝐇𝐎̂𝐍𝐆 𝐓𝐈𝐍 𝐊𝐇𝐀𝐂𝐇 𝐇𝐀̀𝐍𝐆 ༻ •═════✧\n"
        f"👤 *Tên:* {escape_markdown(row[3], version=2)}\n"
        + (f"🔗 *Liên hệ:* {escape_markdown(link_khach, version=2)}\n" if link_khach else "")
)

    return message

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

async def start_update_order(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    keyboard = [
        [InlineKeyboardButton("🔍 Mã Đơn", callback_data="check_ma_don"),
         InlineKeyboardButton("📝 Thông Tin SP", callback_data="check_thong_tin")],
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

async def select_check_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['check_mode'] = query.data
    context.user_data['last_message_id'] = query.message.message_id

    await query.message.edit_reply_markup(reply_markup=None)

    prompt = "🔢 Vui lòng nhập mã đơn hàng:" if query.data == "check_ma_don" else "📝 Vui lòng nhập *Thông tin sản phẩm* cần tìm:"
    await query.message.reply_text(
        prompt,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")]]),
        parse_mode="Markdown" if "thong_tin" in query.data else None
    )
    return INPUT_VALUE

async def input_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    sheet = connect_to_sheet().worksheet("Test")
    data = sheet.get_all_values()

    if check_mode == "check_ma_don":
        for idx, row in enumerate(data):
            if row and row[0] == text:
                context.user_data['selected_row'] = idx + 1
                context.user_data['ma_don'] = row[0]
                message = format_order_message(row)
                buttons = [[
                    InlineKeyboardButton("🛠 Cập nhật đơn", callback_data="start_edit"),
                    InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")
                ]]
                await safe_send(update, message, InlineKeyboardMarkup(buttons))
                return SELECT_FIELD
        await update.message.reply_text("❌ Không tìm thấy mã đơn hàng. Quay về menu chính.")
        return await end_update_success(update, context)

    elif check_mode == "check_thong_tin":
        matched = [(idx + 1, row) for idx, row in enumerate(data) if len(row) > 2 and text.lower() in row[2].lower()]
        if not matched:
            await update.message.reply_text("❌ Không tìm thấy đơn hàng nào phù hợp.")
            return await end_update_success(update, context)

        if len(matched) == 1:
            row_idx, row = matched[0]
            context.user_data['selected_row'] = row_idx
            context.user_data['ma_don'] = row[0]
            message = format_order_message(row)
            buttons = [[
                InlineKeyboardButton("🛠 Cập nhật đơn", callback_data="start_edit"),
                InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")
            ]]
            await safe_send(update, message, InlineKeyboardMarkup(buttons))
            return SELECT_FIELD

        context.user_data['matched_orders'] = matched
        context.user_data['matched_index'] = 0
        await update.message.reply_text("⏳ Đang tải đơn hàng đầu tiên...")
        return await show_matched_order(update, context)

async def show_matched_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction="stay"):
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
    context.user_data["ma_don"] = row[0]

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
    buttons.append([InlineKeyboardButton("🛠 Cập nhật đơn", callback_data="start_edit")])

    await safe_send(update, message, InlineKeyboardMarkup(buttons))
    return SELECT_FIELD

async def input_new_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    sheet = connect_to_sheet().worksheet("Test")
    row_idx = context.user_data.get("selected_row")
    col_idx = context.user_data.get("edit_column")

    if not row_idx or not col_idx:
        await update.message.reply_text("⚠️ Không xác định được dòng cần cập nhật.")
        return await end_update_success(update, context)

    try:
        # Xử lý riêng nếu là giá bán (col 12) hoặc giá nhập (col 11)
        if col_idx in ["11", "12"]:
            gia_text, gia_so = chuan_hoa_gia(text)
            if not gia_text:
                await update.message.reply_text("⚠️ Giá không hợp lệ, vui lòng nhập số nguyên.")
                return ConversationHandler.END
            sheet.update_cell(row_idx, int(col_idx) + 1, gia_text)
        else:
            sheet.update_cell(row_idx, int(col_idx) + 1, text)

        # Nếu cập nhật số ngày đăng ký (col 7), tính lại ngày hết hạn
        if col_idx == "7":
            row = sheet.row_values(row_idx)
            ngay_bat_dau = row[6] if len(row) > 6 else ""
            if ngay_bat_dau:
                ngay_het_han = tinh_ngay_het_han(ngay_bat_dau, text)
                sheet.update_cell(row_idx, 9, ngay_het_han)

        updated = sheet.row_values(row_idx)
        message = format_order_message(updated)
        await update.message.reply_text(message, parse_mode="MarkdownV2")

    except Exception as e:
        await update.message.reply_text(f"❌ Cập nhật thất bại: {str(e)}")

    return await end_update_success(update, context)

async def start_edit_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📆 Số Ngày Đăng Ký", callback_data="edit_col_7"),
         InlineKeyboardButton("💵 Giá Bán", callback_data="edit_col_12")],
        [InlineKeyboardButton("🚚 Nguồn Cấp Hàng", callback_data="edit_col_10"),
         InlineKeyboardButton("🧾 Giá Nhập", callback_data="edit_col_11")],
        [InlineKeyboardButton("👤 Tên Khách Hàng", callback_data="edit_col_3"),
         InlineKeyboardButton("🔗 Link Khách", callback_data="edit_col_4")],
        [InlineKeyboardButton("❌ Kết Thúc", callback_data="end_update_with_cancel")]
    ]
    await update.callback_query.answer()
    await update.callback_query.message.edit_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text(
        "📋 Vui lòng chọn nội dung cần chỉnh sửa:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_FIELD

async def choose_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_column'] = query.data.split("_")[-1]
    await query.message.edit_reply_markup(reply_markup=None)
    msg = await query.message.reply_text("✏️ Vui lòng nhập nội dung cần chỉnh sửa:")
    context.user_data["last_message_id"] = msg.message_id
    return INPUT_NEW_VALUE

async def end_update_with_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.edit_text("❌ Đã hủy cập nhật đơn.")
        except Exception as e:
            logger.warning(f"[❌ Không thể sửa tin nhắn cũ]: {e}")
        await show_main_selector(update, context, edit=False)
    elif update.message:
        await update.message.reply_text("❌ Đã hủy cập nhật đơn.")
        await show_main_selector(update, context, edit=False)
    return ConversationHandler.END

async def end_update_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                CallbackQueryHandler(select_check_mode, pattern="^check_thong_tin$"),
            ],
            INPUT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_value_handler)],
            SELECT_FIELD: [
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "prev"), pattern="^prev_matched$"),
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "next"), pattern="^next_matched$"),
                CallbackQueryHandler(start_edit_update, pattern="^start_edit$"),
                CallbackQueryHandler(choose_field_to_edit, pattern="^edit_col_.*")
            ],
            INPUT_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_value_handler)]
        },
        fallbacks=[
            CallbackQueryHandler(end_update_with_cancel, pattern="^end_update_with_cancel$"),
            CommandHandler("cancel", end_update_with_cancel)
        ],
        name="update_order_conversation",
        persistent=False
    )