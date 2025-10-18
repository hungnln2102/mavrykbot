import logging
import traceback
import html
import json
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

#
# === THAY ĐỔI 1: Định nghĩa ID Group và Topic Lỗi ===
#
ERROR_GROUP_ID = "-1002934465528"
ERROR_TOPIC_ID = 6


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bắt, ghi log và gửi tất cả lỗi vào Topic 'Notify Error'."""
    
    # 1. Ghi log lỗi ra console/file (Không thay đổi)
    logger.error("Lỗi xảy ra khi xử lý một bản cập nhật:", exc_info=context.error)

    # 2. Kiểm tra lỗi 'Event loop is closed' (Không thay đổi)
    # Lỗi này xảy ra khi tắt bot, chúng ta có thể bỏ qua
    if isinstance(context.error, RuntimeError) and str(context.error) == "Event loop is closed":
        logger.warning("Event loop đã đóng (do tắt bot). Bỏ qua gửi thông báo lỗi.")
        return

    # 3. Lấy thông tin traceback (Không thay đổi)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # 4. Chuẩn bị thông báo lỗi (Không thay đổi)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"❌ *ĐÃ XẢY RA LỖI HỆ THỐNG*\n\n"
        f"Một lỗi nghiêm trọng đã xảy ra, vui lòng kiểm tra:\n\n"
        f"*Thông tin Update:*\n"
        f"<pre>{html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"*Traceback chi tiết:*\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    #
    # === THAY ĐỔI 2: Gửi thông báo lỗi đến đúng Group và Topic ===
    #
    try:
        # Giới hạn độ dài tin nhắn (Telegram có giới hạn 4096 ký tự)
        max_length = 4096
        if len(message) > max_length:
            truncated_message = message[:max_length - 20] + "\n... (NỘI DUNG QUÁ DÀI)"
        else:
            truncated_message = message
            
        await context.bot.send_message(
            chat_id=ERROR_GROUP_ID,         # Gửi vào Group chung
            text=truncated_message,
            parse_mode=ParseMode.HTML,
            message_thread_id=ERROR_TOPIC_ID  # Gửi vào Topic "Notify Error"
        )
    except Exception as e:
        logger.error(f"LỖI CỦA LỖI: Không thể gửi thông báo lỗi cho admin: {e}")