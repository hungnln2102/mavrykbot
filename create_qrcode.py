# create_qrcode.py (Đã tối ưu)

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging
import requests
from menu import show_outer_menu

logger = logging.getLogger(__name__)

# Các trạng thái
ASK_AMOUNT, ASK_NOTE = range(2)

async def handle_create_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu quy trình, edit tin nhắn hiện tại để hỏi số tiền."""
    query = update.callback_query
    await query.answer()
    
    # CẢI TIỆN UX: Lưu message_id để edit, không tạo tin nhắn mới
    context.user_data['qr_message_id'] = query.message.message_id
    
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_qr")]]
    await query.edit_message_text(
        text="💵 Vui lòng nhập *số tiền cần thanh toán* (ví dụ: 250 hoặc 250.5):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_AMOUNT

async def ask_qr_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý số tiền và hỏi nội dung chuyển khoản."""
    amount_raw = update.message.text
    # CẢI TIỆN UX: Xóa tin nhắn của người dùng
    await update.message.delete()
    
    try:
        # TỐI ƯU: Sử dụng logic xử lý số tiền đã được chuẩn hóa
        sanitized_text = amount_raw.strip().replace(',', '.')
        numeric_value = float(sanitized_text)
        amount = int(numeric_value * 1000)
        context.user_data["qr_amount"] = str(amount)
    except ValueError:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['qr_message_id'],
            text="❌ Số tiền không hợp lệ. Vui lòng chỉ nhập số.\n\n"
                 "💵 Vui lòng nhập lại *số tiền cần thanh toán*:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_qr")]])
        )
        return ASK_AMOUNT

    # CẢI TIỆN UX: Edit tin nhắn hiện tại để hỏi nội dung
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data['qr_message_id'],
        text="📝 Vui lòng nhập *nội dung thanh toán* (ví dụ: Mua Key Adobe):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_qr")]])
    )
    return ASK_NOTE

async def send_qr_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gửi ảnh QR code, sau đó quay về menu chính và kết thúc quy trình."""
    note = update.message.text.strip()
    await update.message.delete()
    
    gia_value = context.user_data.get("qr_amount")
    
    note_encoded = requests.utils.quote(note)

    qr_url = (
        f"https://img.vietqr.io/image/VPB-9183400998-compact2.png"
        f"?amount={gia_value}"
        f"&addInfo={note_encoded}"
        f"&accountName=NGO LE NGOC HUNG"
    )

    caption = (
        f"Số tài khoản: `9183400998`\n"
        f"Ngân hàng: *VP Bank (TMCP Việt Nam Thịnh Vượng)*\n"
        f"Chủ tài khoản: *NGO LE NGOC HUNG*\n"
        f"💵 *Số tiền:* `{int(gia_value):,} đ`\n"
        f"📝 *Nội dung:* `{note}`\n"
        f"──────────────\n"
        f"Cảm ơn quý khách đã tin tưởng dịch vụ!"
    )

    main_message_id = context.user_data.get('qr_message_id')
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=main_message_id)
    except Exception as e:
        logger.warning(f"Không thể xóa tin nhắn tạo QR: {e}")

    await update.effective_chat.send_photo(photo=qr_url, caption=caption, parse_mode="Markdown")
    
    # THÊM LẠI: Gọi lại menu chính sau khi gửi QR
    await show_outer_menu(update, context)

    # Dọn dẹp context và kết thúc
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy quy trình và quay về menu chính."""
    query = update.callback_query
    await query.answer()
    
    # Dọn dẹp context
    context.user_data.clear()
    
    # Quay về menu chính
    await show_outer_menu(update, context)
    return ConversationHandler.END

# Đăng ký ConversationHandler (giữ nguyên)
qr_conversation = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_create_qr, pattern='^create_qr$')],
    states={
        ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_qr_note)],
        ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_qr_image)],
    },
    fallbacks=[CallbackQueryHandler(cancel_qr, pattern='^cancel_qr$')],
    per_message=False # Thêm vào để tránh cảnh báo
)