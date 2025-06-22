from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)
from telegram.helpers import escape_markdown
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import re
from menu import show_outer_menu
ASK_AMOUNT, ASK_NOTE = range(2)

# 🟩 Bắt đầu quy trình tạo QR
async def handle_create_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Huỷ tạo QR", callback_data="cancel_qr")]])
    await query.message.reply_text(
        "\U0001F4B5 Vui lòng nhập *số tiền cần thanh toán* (vd: 250 hoặc 250.5):",
        parse_mode="Markdown",
        reply_markup=cancel_button
    )
    return ASK_AMOUNT

# 🟨 Hỏi nội dung chuyển khoản
async def ask_qr_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", ".")
    if not re.match(r'^\d+(\.\d{1,2})?$', raw):
        await update.message.reply_text("❌ Số tiền không hợp lệ. Vui lòng nhập lại.")
        return ASK_AMOUNT

    try:
        parts = raw.split(".")
        amount = int(parts[0]) * 1000
        if len(parts) == 2:
            decimal_part = parts[1].ljust(2, "0")
            amount += int(decimal_part[:2]) * 10
        context.user_data["qr_amount"] = str(amount)
    except:
        await update.message.reply_text("❌ Có lỗi khi xử lý số tiền.")
        return ASK_AMOUNT

    cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Huỷ tạo QR", callback_data="cancel_qr")]])
    await update.message.reply_text(
        "\U0001F4DD Vui lòng nhập *nội dung thanh toán* (vd: Mua Key Adobe):",
        parse_mode="Markdown",
        reply_markup=cancel_button
    )
    return ASK_NOTE

# 🟥 Gửi QR code sau khi có đủ thông tin
async def send_qr_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    context.user_data["qr_note"] = note

    gia_value = context.user_data.get("qr_amount")
    ma_don = note

    qr_url = (
        f"https://img.vietqr.io/image/VPB-mavpre-compact2.png"
        f"?amount={gia_value}"
        f"&addInfo={ma_don.replace(' ', '%20')}"
        f"&accountName=NGO%20LE%20NGOC%20HUNG"
    )

    caption = (
        f"💳Số Tài Khoản: 9183400998\n"
        f"🏦Ngân Hàng: VP Bank\n"
        f"👨Chủ Tài Khoản: NGO LE NGOC HUNG\n"
        f"\U0001F4B0 *Số Tiền Cần Thanh Toán:* {gia_value} đ\n"
        f"\U0001F4DD *Nội Dung Thanh Toán:* {note}\n"
        f"============\n"
        f"Cám ơn quý khách đã tin tưởng dịch vụ *Mavryk Premium*"
    )

    await update.message.reply_photo(photo=qr_url, caption=caption, parse_mode="Markdown")
    await show_outer_menu(update, context)  # ✅ Gọi lại menu ngoài sau khi gửi QR
    return ConversationHandler.END


# ❌ Huỷ tạo QR code
async def cancel_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ Đã huỷ tạo QR thanh toán.")
    return ConversationHandler.END

# 🧩 Đăng ký ConversationHandler
qr_conversation = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_create_qr, pattern='^create_qr$')],
    states={
        ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_qr_note)],
        ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_qr_image)],
    },
    fallbacks=[CallbackQueryHandler(cancel_qr, pattern='^cancel_qr$')],
)
