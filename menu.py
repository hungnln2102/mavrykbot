from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

ADMIN_USER_IDS = [510811276]

# Menu ngoài cùng: Chọn phân hệ
async def show_outer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("👤 Khách Hàng", callback_data='menu_customer'),
            InlineKeyboardButton("🏬 Shop", callback_data='menu_shop')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "🔽 *Chọn phân hệ làm việc:*"

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            await update.callback_query.message.delete()
            await update.effective_chat.send_message(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# Menu SHOP: gồm 5 nút chia thành 3 hàng
async def show_main_selector(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    keyboard = [
        [
            InlineKeyboardButton("📝 Thêm Đơn Hàng", callback_data='add'),
            InlineKeyboardButton("🔄 Cập Nhật Đơn", callback_data='update')
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
        try:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            await update.callback_query.message.delete()
            await update.effective_chat.send_message(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')