from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram

ADMIN_USER_IDS = [510811276]

# Menu ngoài cùng: Chọn phân hệ
async def show_outer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("👤 Đơn Chưa Thanh Toán", callback_data='unpaid_orders'),
            InlineKeyboardButton("🏬 Shop", callback_data='menu_shop')
        ],
        [
            InlineKeyboardButton("💰 Thanh Toán Nguồn", callback_data='payment_source')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "🔽 *Chọn phân hệ làm việc:*"

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                message, reply_markup=reply_markup, parse_mode='Markdown'
            )
        except telegram.error.BadRequest as e:
            if "message to edit not found" in str(e).lower() or "no text" in str(e).lower():
                try:
                    await update.callback_query.message.delete()
                except:
                    pass
                await update.effective_chat.send_message(
                    message, reply_markup=reply_markup, parse_mode='Markdown'
                )
            else:
                raise e
    elif update.message:
        await update.message.reply_text(
            message, reply_markup=reply_markup, parse_mode='Markdown'
        )


# Menu SHOP: gồm 5 nút chia thành 3 hàng
async def show_main_selector(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
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

    if update.callback_query and edit:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        # ✅ Gửi menu mới bằng tin nhắn mới, không sửa tin cũ
        await update.effective_chat.send_message(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
