import logging
import traceback
import html
import json
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

ERROR_GROUP_ID = "-1002934465528"
ERROR_TOPIC_ID = 6


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bắt, ghi log và gửi tất cả lỗi vào Topic 'Notify Error'."""
    
    logger.error("Lỗi xảy ra khi xử lý một bản cập nhật:", exc_info=context.error)

    if isinstance(context.error, RuntimeError) and str(context.error) == "Event loop is closed":
        logger.warning("Event loop đã đóng (do tắt bot). Bỏ qua gửi thông báo lỗi.")
        return

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"❌ *ĐÃ XẢY RA LỖI HỆ THỐNG*\n\n"
        f"Một lỗi nghiêm trọng đã xảy ra, vui lòng kiểm tra:\n\n"
        f"*Thông tin Update:*\n"
        f"<pre>{html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"*Traceback chi tiết:*\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    try:
        max_length = 4096
        if len(message) > max_length:
            truncated_message = message[:max_length - 20] + "\n... (NỘI DUNG QUÁ DÀI)"
        else:
            truncated_message = message
            
        await context.bot.send_message(
            chat_id=ERROR_GROUP_ID,
            text=truncated_message,
            parse_mode=ParseMode.HTML,
            message_thread_id=ERROR_TOPIC_ID
        )
    except Exception as e:
        logger.error(f"LỖI CỦA LỖI: Không thể gửi thông báo lỗi cho admin: {e}")