# error_handler.py (Phiên bản đã sửa lỗi rút gọn)

import logging
import traceback
import html
import json
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import config 

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bắt, ghi log và gửi tất cả lỗi dựa trên tệp config."""
    
    # 1. Ghi log (Không thay đổi)
    logger.error("Lỗi xảy ra khi xử lý một bản cập nhật:", exc_info=context.error)

    # 2. Bỏ qua lỗi 'Event loop' (Không thay đổi)
    if isinstance(context.error, RuntimeError) and str(context.error) == "Event loop is closed":
        logger.warning("Event loop đã đóng (do tắt bot). Bỏ qua gửi thông báo lỗi.")
        return

    # 3. Chuẩn bị message
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    # === BẮT ĐẦU SỬA LỖI RÚT GỌN (TRUNCATE) ===
    
    # Xây dựng các phần của tin nhắn
    header = "❌ *ĐÃ XẢY RA LỖI HỆ THỐNG*\n\n"
    update_info = (
        f"*Thông tin Update:*\n"
        f"<pre>{html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
    )
    traceback_header = "*Traceback chi tiết:*\n"
    
    # Tính toán độ dài tối đa cho phép của traceback
    # Giới hạn của Telegram là 4096.
    # Ta trừ đi độ dài của các phần khác và 20 ký tự cho thẻ </pre> và '... (rút gọn)'
    max_tb_len = 4096 - len(header) - len(update_info) - len(traceback_header) - 20 

    if len(tb_string) > max_tb_len:
        tb_string = tb_string[:max_tb_len] + "\n... (NỘI DUNG ĐÃ RÚT GỌN)"
        
    # Tạo tin nhắn cuối cùng, đảm bảo thẻ <pre> luôn được đóng
    message = (
        f"{header}"
        f"{update_info}"
        f"{traceback_header}"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    # === KẾT THÚC SỬA LỖI RÚT GỌN ===

    # 4. Gửi tin nhắn (Logic không đổi)
    chat_id_to_send = None
    topic_id_to_send = None

    if config.SEND_ERROR_TO_TOPIC:
        chat_id_to_send = config.ERROR_GROUP_ID
        topic_id_to_send = config.ERROR_TOPIC_ID
    else:
        chat_id_to_send = config.ADMIN_CHAT_ID
        topic_id_to_send = None

    try:
        await context.bot.send_message(
            chat_id=chat_id_to_send,
            text=message, # Gửi tin nhắn đã được rút gọn an toàn
            parse_mode=ParseMode.HTML,
            message_thread_id=topic_id_to_send
        )
    except Exception as e:
        logger.error(f"LỖI CỦA LỖI: Không thể gửi thông báo lỗi đến {chat_id_to_send}: {e}")