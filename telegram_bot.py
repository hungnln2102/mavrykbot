import logging
from telegram import Bot
from utils import escape_mdv2

# --- Configuration ---
ADMIN_CHAT_ID = "510811276"
logger = logging.getLogger(__name__)

# --- ADD THIS HELPER FUNCTION ---
def format_currency(value):
    """Formats a number into a currency string with commas."""
    try:
        # Converts to float, formats with commas, and removes decimal part for whole numbers
        return "{:,.0f}".format(float(value))
    except (ValueError, TypeError):
        # Returns "0" if the value is not a valid number
        return "0"

async def send_renewal_success_notification(bot: Bot, order_details: dict):
    """
    Formats and sends a successful renewal notification via Telegram.
    """
    if not order_details:
        logger.warning("send_notification was called but no order details were provided.")
        return

    try:
        # Escape dynamic data for MarkdownV2 safety
        ma_don_hang = escape_mdv2(order_details.get('ID_DON_HANG'))
        san_pham = escape_mdv2(order_details.get('SAN_PHAM'))
        thong_tin_don = escape_mdv2(order_details.get('THONG_TIN_DON'))
        ngay_dang_ky = escape_mdv2(order_details.get('NGAY_DANG_KY'))
        ngay_het_han = escape_mdv2(order_details.get('HET_HAN'))
        
        # Get and format new data
        nguon = escape_mdv2(order_details.get('NGUON'))
        gia_nhap = format_currency(order_details.get('GIA_NHAP'))
        gia_ban = format_currency(order_details.get('GIA_BAN'))

        slot_info = ""
        slot_data = order_details.get('SLOT')
        if slot_data and str(slot_data).strip():
            slot_info = f"\n📦 *Slot:* {escape_mdv2(slot_data)}"

        # Create the message with the new layout
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
            chat_id=ADMIN_CHAT_ID,
            text=message,
            parse_mode='MarkdownV2'
        )
        logging.info(f"Successfully sent renewal notification for ID {order_details.get('ID_DON_HANG')}")

    except Exception as e:
        logging.error(f"Error sending Telegram notification for ID {order_details.get('ID_DON_HANG')}: {e}")