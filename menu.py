from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram
import logging

ADMIN_USER_IDS = [510811276]
logger = logging.getLogger(__name__)

# Menu ngoài cùng: Chọn phân hệ
async def show_outer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Hiển thị menu chính. Tự động xử lý việc edit tin nhắn văn bản
    hoặc thay thế tin nhắn media.
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Thêm Đơn", callback_data='add'),
            InlineKeyboardButton("🔄 Xem Đơn", callback_data='update'),
            InlineKeyboardButton("⏰ Đơn Đến Hạn", callback_data='expired')
        ],
        [
            InlineKeyboardButton("🔚 Quay Lại Menu Chính", callback_data='back_to_menu')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🔽 *Chọn phân hệ làm việc:*"

    query = update.callback_query
    
    try:
        if query:
            # Nếu tin nhắn gốc là tin nhắn văn bản, ta chỉ cần edit nó.
            if query.message.text:
                logger.info("🔹 show_outer_menu: Editing text message.")
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            # Nếu tin nhắn gốc là media (hình ảnh), ta phải xóa và gửi mới.
            else:
                logger.info("🔹 show_outer_menu: Replacing media message with text menu.")
                await query.message.delete()
                await query.message.chat.send_message(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        # Nếu người dùng gõ lệnh /start hoặc /menu
        elif update.message:
            logger.info("🔹 show_outer_menu: Sending new menu message.")
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except telegram.error.BadRequest as e:
        # Giữ lại khối except này như một lớp bảo vệ cuối cùng cho các lỗi không lường trước
        logger.error(f"❌ Lỗi không mong muốn trong show_outer_menu: {e}")
        try:
            await update.effective_chat.send_message(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as final_e:
            logger.critical(f"💣 Không thể gửi menu cho người dùng: {final_e}")


# Menu SHOP: gồm 5 nút chia thành 3 hàng
async def show_main_selector(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    logger.info(f"🔹 show_main_selector(edit={edit}) called")

    keyboard = [
        [
            InlineKeyboardButton("📝 Thêm Đơn Hàng", callback_data='add'),
            InlineKeyboardButton("🔄 Xem Đơn Hàng", callback_data='update')
        ],
        [
            InlineKeyboardButton("⏰ Đơn Đến Hạn", callback_data='expired'),
            InlineKeyboardButton("🗑️ Xóa Đơn", callback_data='delete_order')
        ],
        [
            InlineKeyboardButton("🔚 Kết Thúc", callback_data='back_to_menu')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "🔽 *Chọn chức năng:*"

    try:
        if update.callback_query and edit:
            logger.info("🔄 show_main_selector: edit_message_text")
            await update.callback_query.edit_message_text(
                text=message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            logger.info("✉️ show_main_selector: send_message")
            await update.effective_chat.send_message(
                text=message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except telegram.error.BadRequest as e:
        logger.warning(f"❌ Lỗi trong show_main_selector: {e}")
        await update.effective_chat.send_message(
            text=message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
