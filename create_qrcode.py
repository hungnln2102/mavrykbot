# create_qrcode.py (An toàn caption + gửi ảnh bytes)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)
from telegram.constants import ParseMode
import logging
import html as htmlmod
from io import BytesIO
import requests
from urllib.parse import quote_plus

from menu import show_outer_menu

logger = logging.getLogger(__name__)

# Các trạng thái
ASK_AMOUNT, ASK_NOTE = range(2)

def _fmt_vnd(amount: int) -> str:
    # 1234567 -> '1.234.567'
    return f"{amount:,}".replace(",", ".")

async def handle_create_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu quy trình, edit tin nhắn hiện tại để hỏi số tiền."""
    query = update.callback_query
    await query.answer()

    # Lưu message_id để edit (UX tốt, không tạo tin nhắn mới)
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
    amount_raw = update.message.text or ""
    # Xóa tin nhắn của người dùng cho gọn
    try:
        await update.message.delete()
    except Exception:
        pass

    try:
        sanitized_text = amount_raw.strip().replace(',', '.')
        numeric_value = float(sanitized_text)
        # Người dùng nhập '250' nghĩa là 250k
        amount_vnd = int(numeric_value * 1000)
        if amount_vnd <= 0:
            raise ValueError("non-positive amount")
        context.user_data["qr_amount"] = amount_vnd
    except Exception:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['qr_message_id'],
            text=(
                "❌ Số tiền không hợp lệ. Vui lòng chỉ nhập số.\n\n"
                "💵 Vui lòng nhập lại *số tiền cần thanh toán*:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_qr")]])
        )
        return ASK_AMOUNT

    # Hỏi nội dung thanh toán
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data['qr_message_id'],
        text="📝 Vui lòng nhập *nội dung thanh toán* (ví dụ: Mua Key Adobe):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_qr")]])
    )
    return ASK_NOTE

async def send_qr_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tạo & gửi ảnh QR, sau đó quay về menu chính và kết thúc."""
    note = (update.message.text or "").strip()
    # Xóa tin nhắn người dùng
    try:
        await update.message.delete()
    except Exception:
        pass

    amount_vnd = int(context.user_data.get("qr_amount", 0))

    # Encode an toàn cho tham số URL
    note_encoded = quote_plus(note)
    account_name = "NGO LE NGOC HUNG"
    account_name_encoded = quote_plus(account_name)

    # VietQR PNG URL
    qr_url = (
        "https://img.vietqr.io/image/VPB-9183400998-compact2.png"
        f"?amount={amount_vnd}"
        f"&addInfo={note_encoded}"
        f"&accountName={account_name_encoded}"
    )

    # Tải ảnh về bytes để Telegram không phải đi lấy từ ngoài (tránh 400)
    buf = BytesIO()
    try:
        resp = requests.get(qr_url, timeout=15)
        resp.raise_for_status()
        buf.write(resp.content)
        buf.seek(0)
    except Exception as e:
        logger.exception("Tải ảnh QR thất bại: %s", e)
        await update.effective_chat.send_message(
            "❌ Không tạo được ảnh QR lúc này. Vui lòng thử lại sau."
        )
        # Quay về menu
        await show_outer_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    # Caption dùng HTML (an toàn ký tự đặc biệt)
    note_safe = htmlmod.escape(note)
    caption_html = (
        "<b>Thông tin chuyển khoản</b>\n"
        "Số tài khoản: <code>9183400998</code>\n"
        "Ngân hàng: <b>VP Bank (TMCP Việt Nam Thịnh Vượng)</b>\n"
        f"Chủ tài khoản: <b>{htmlmod.escape(account_name)}</b>\n"
        f"💵 Số tiền: <b>{_fmt_vnd(amount_vnd)} đ</b>\n"
        f"📝 Nội dung: <code>{note_safe}</code>\n"
        "──────────────\n"
        "Cảm ơn quý khách đã tin tưởng dịch vụ!"
    )

    # Xóa message hướng dẫn (nếu còn)
    main_message_id = context.user_data.get('qr_message_id')
    if main_message_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=main_message_id
            )
        except Exception as e:
            logger.warning("Không thể xóa tin nhắn tạo QR: %s", e)

    # Gửi ảnh từ bytes + caption HTML
    try:
        await update.effective_chat.send_photo(
            photo=buf,
            caption=caption_html,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.exception("send_photo lỗi: %s", e)
        await update.effective_chat.send_message(
            "❌ Gửi QR thất bại (caption/ảnh). Vui lòng thử lại."
        )

    # Quay về menu
    await show_outer_menu(update, context)

    # Dọn dẹp
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy quy trình và quay về menu chính."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await show_outer_menu(update, context)
    return ConversationHandler.END

# ConversationHandler
qr_conversation = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_create_qr, pattern='^create_qr$')],
    states={
        ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_qr_note)],
        ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_qr_image)],
    },
    fallbacks=[CallbackQueryHandler(cancel_qr, pattern='^cancel_qr$')],
    per_message=False,
)
