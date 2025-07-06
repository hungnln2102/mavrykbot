# delete_order.py (Hoàn thiện cuối cùng)

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from utils import connect_to_sheet, escape_mdv2 # Import hàm escape chuẩn
from menu import show_main_selector
from column import SHEETS, ORDER_COLUMNS

logger = logging.getLogger(__name__)

# Các trạng thái mới
ASK_ID, CONFIRM_DELETE = range(2)

def format_order_info(row_data):
    """Tạo nội dung tin nhắn chi tiết hơn cho đơn hàng cần xóa."""
    def get_val(col_name):
        try: return row_data[ORDER_COLUMNS[col_name]].strip()
        except (IndexError, KeyError): return ""

    ma_don_md = escape_mdv2(get_val("ID_DON_HANG"))
    san_pham_md = escape_mdv2(get_val("SAN_PHAM"))
    ten_khach_md = escape_mdv2(get_val("TEN_KHACH"))
    ngay_het_han_md = escape_mdv2(get_val("HET_HAN"))
    con_lai_md = escape_mdv2(get_val("CON_LAI"))
    gia_ban_md = escape_mdv2(get_val("GIA_BAN"))

    return (
        f"🗑️ *BẠN CÓ CHẮC CHẮN MUỐN XÓA?*\n"
        f"_{escape_mdv2('Hành động này không thể hoàn tác.')}_\n\n"
        f"🧾 *Thông tin đơn hàng sẽ bị xóa:*\n"
        f"\\- *Mã đơn:* `{ma_don_md}`\n"
        f"\\- *Sản phẩm:* {san_pham_md}\n"
        f"\\- *Khách hàng:* {ten_khach_md}\n"
        f"\\- *Hết hạn:* {ngay_het_han_md} `(còn {con_lai_md} ngày)`\n"
        f"\\- *Giá bán:* {gia_ban_md}"
    )

async def start_delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu quy trình xóa, hỏi mã đơn."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['delete_message_id'] = query.message.message_id
    
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_delete")]]
    await query.edit_message_text(
        text="🗑️ Vui lòng nhập *Mã đơn hàng* bạn muốn xóa:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_ID

async def handle_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Nhận mã đơn, tìm trong sheet, cache lại và hiển thị xác nhận."""
    ma_don_to_find = update.message.text.strip()
    await update.message.delete()
    
    main_message_id = context.user_data.get('delete_message_id')
    chat_id = update.effective_chat.id
    
    # SỬA LỖI: Sử dụng escape và MarkdownV2
    ma_don_md = escape_mdv2(ma_don_to_find)
    await context.bot.edit_message_text(
        chat_id=chat_id, 
        message_id=main_message_id, 
        text=f"🔎 Đang tìm mã đơn `{ma_don_md}`{escape_mdv2('...')}",
        parse_mode="MarkdownV2"
    )
    
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        all_data = sheet.get_all_values()
        
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > ORDER_COLUMNS["ID_DON_HANG"] and row[ORDER_COLUMNS["ID_DON_HANG"]].strip() == ma_don_to_find:
                context.user_data['order_to_delete'] = {"data": row, "row_index": i}
                
                message_text = format_order_info(row)
                keyboard = [[
                    InlineKeyboardButton("✅ Có, xóa ngay", callback_data="confirm_delete"),
                    InlineKeyboardButton("❌ Không, hủy bỏ", callback_data="cancel_delete")
                ]]
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=main_message_id,
                    text=message_text,
                    parse_mode="MarkdownV2",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CONFIRM_DELETE
        
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=main_message_id,
            text=escape_mdv2(f"❌ Không tìm thấy đơn hàng với mã `{ma_don_to_find}`."),
            parse_mode="MarkdownV2"
        )
        return await end_flow(update, context)

    except Exception as e:
        logger.error(f"Lỗi khi truy cập Sheet để xóa: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=main_message_id, text=escape_mdv2("⚠️ Đã xảy ra lỗi khi truy cập dữ liệu."))
        return await end_flow(update, context)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xác nhận và thực hiện xóa trên Google Sheet, sau đó xóa cache."""
    query = update.callback_query
    await query.answer("Đang xóa...")
    
    order_to_delete = context.user_data.get('order_to_delete')
    if not order_to_delete:
        await query.edit_message_text(escape_mdv2("❌ Lỗi: Không có thông tin đơn hàng để xóa."))
        return await end_flow(update, context)

    row_index = order_to_delete["row_index"]
    ma_don = order_to_delete["data"][ORDER_COLUMNS["ID_DON_HANG"]]
    
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.delete_rows(row_index)
        
        context.user_data.pop('order_sheet_cache', None)
        
        ma_don_md = escape_mdv2(ma_don)
        await query.edit_message_text(
            text=f"✅ Đơn hàng `{ma_don_md}` đã được *xóa thành công*\\!",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Lỗi khi xóa đơn: {e}")
        await query.edit_message_text(escape_mdv2("⚠️ Đã xảy ra lỗi khi xóa đơn hàng."))
        
    return await end_flow(update, context)

async def end_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hàm chung để kết thúc quy trình và dọn dẹp."""
    context.user_data.clear()
    await asyncio.sleep(2)
    # Gọi lại menu chính
    if update.callback_query:
        await show_main_selector(update, context, edit=True)
    return ConversationHandler.END

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy bỏ thao tác."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(escape_mdv2("❌ Đã hủy thao tác xóa."))
    return await end_flow(update, context)

def get_delete_order_conversation_handler():
    """Tạo và trả về một ConversationHandler thống nhất."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_delete_order, pattern="^delete_order$")
        ],
        states={
            ASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id_input)],
            CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete, pattern="^confirm_delete$")],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$")
        ],
        name="unified_delete_conversation",
        persistent=False,
        allow_reentry=True
    )