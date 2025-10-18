import logging
from telegram import Bot
from utils import escape_mdv2

ADMIN_CHAT_ID = "510811276"
logger = logging.getLogger(__name__)

NOTIFICATION_GROUP_ID = "-1002934465528"
RENEWAL_TOPIC_ID = 2


def format_currency(value):
    """Formats a number into a currency string with commas."""
    try:
        return "{:,.0f}".format(float(value))
    except (ValueError, TypeError):
        return "0"

async def send_renewal_success_notification(
    bot: Bot, 
    order_details: dict,
    target_chat_id: str = NOTIFICATION_GROUP_ID,
    target_topic_id: int = RENEWAL_TOPIC_ID
):
    if not order_details:
        logger.warning("send_notification được gọi nhưng không có chi tiết đơn hàng.")
        return

    try:
        ma_don_hang = escape_mdv2(order_details.get('ID_DON_HANG'))
        san_pham = escape_mdv2(order_details.get('SAN_PHAM'))
        thong_tin_don = escape_mdv2(order_details.get('THONG_TIN_DON'))
        ngay_dang_ky = escape_mdv2(order_details.get('NGAY_DANG_KY'))
        ngay_het_han = escape_mdv2(order_details.get('HET_HAN'))
        
        nguon = escape_mdv2(order_details.get('NGUON'))
        gia_nhap = format_currency(order_details.get('GIA_NHAP'))
        gia_ban = format_currency(order_details.get('GIA_BAN'))

        slot_info = ""
        slot_data = order_details.get('SLOT')
        if slot_data and str(slot_data).strip():
            slot_info = f"\n📦 *Slot:* {escape_mdv2(slot_data)}"

        message = (
            f"✅ *GIA HẠN TỰ ĐỘNG THÀNH CÔNG*\n\n"
            
            f"✧•─── *Thông Tin Đơn Hàng* ───•✧\n"
            f"🧾 *Mã Đơn:* `{ma_don_hang}`\n"
            f"🏷️ *Sản phẩm:* {san_pham}\n"
            f"📝 *Thông tin:* {thong_tin_don}"
            f"{slot_info}\n"
            f"🗓️ *Ngày ĐK Mới:* {ngay_dang_ky}\n"
            f"⏳ *Hết Hạn Mới:* *{ngay_het_han}*\n"
            f"📤 *Giá Bán:* {gia_ban}đ\n\n"

            f"✧•──── *Thông Tin Nguồn* ────•✧\n"
            f"🚚 *Nguồn:* {nguon}\n"
            f"📥 *Giá Nhập:* {gia_nhap}đ"
        )

        await bot.send_message(
            chat_id=target_chat_id,
            text=message,
            parse_mode='MarkdownV2',
            message_thread_id=target_topic_id
        )
        logging.info(f"Đã gửi thông báo gia hạn cho ID {order_details.get('ID_DON_HANG')} tới topic {target_topic_id}")

    except Exception as e:
        logging.error(f"Lỗi khi gửi thông báo Telegram cho ID {order_details.get('ID_DON_HANG')}: {e}")