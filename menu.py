from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram
import logging

ADMIN_USER_IDS = [510811276]
logger = logging.getLogger(__name__)

async def show_outer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("👤 Đơn Chưa Thanh Toán", callback_data='unpaid_orders'),
            InlineKeyboardButton("🏬 Shop", callback_data='menu_shop')
        ],
        [
            InlineKeyboardButton("💰 Tạo QR Thanh Toán", callback_data='create_qr'),
            InlineKeyboardButton("💰 Thanh Toán Nguồn", callback_data='payment_source')
        ],
        [
            InlineKeyboardButton("💸 Hoàn Tiền", callback_data='start_refund')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🔽 *Chọn phân hệ làm việc:*"
    query = update.callback_query
    try:
        if query:
            if query.message.text:
                logger.info("🔹 show_outer_menu: Editing text message.")
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                logger.info("🔹 show_outer_menu: Replacing media message with text menu.")
                await query.message.delete()
                await query.message.chat.send_message(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        elif update.message:
            logger.info("🔹 show_outer_menu: Sending new menu message.")
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except telegram.error.BadRequest as e:
        logger.error(f"❌ Lỗi không mong muốn trong show_outer_menu: {e}")
        try:
            await update.effective_chat.send_message(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as final_e:
            logger.critical(f"💣 Không thể gửi menu cho người dùng: {final_e}")

async def show_main_selector(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    edit: bool = False,
    text: str | None = None,
) -> None:
    keyboard = [
        [
            InlineKeyboardButton("📝 Thêm Đơn", callback_data="add"),
            InlineKeyboardButton("🔄 Xem/Chỉnh Đơn", callback_data="update"),
        ],
        [
            InlineKeyboardButton("📥 Nhập Hàng", callback_data="nhap_hang"),
            InlineKeyboardButton("⬅️ Về menu chính", callback_data="back_to_menu"),
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    q = update.callback_query
    msg = q.message if q else update.effective_message
    body = text or "👉 Chọn chức năng:"
    try:
        if q:
            await q.answer()
            if getattr(msg, "text", None):
                await msg.edit_text(body, reply_markup=markup, parse_mode="Markdown")
            else:
                await msg.delete()
                await msg.chat.send_message(body, reply_markup=markup, parse_mode="Markdown")
        else:
            await msg.reply_text(body, reply_markup=markup, parse_mode="Markdown")
    except telegram.error.BadRequest as e:
        logger.warning(f"show_main_selector BadRequest: {e}")
        await update.effective_chat.send_message(body, reply_markup=markup, parse_mode="Markdown")