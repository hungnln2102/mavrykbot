import logging
from telegram import Bot

# --- Import hàm escape có sẵn từ utils.py ---
from utils import escape_mdv2

# --- Cấu hình ---
ADMIN_CHAT_ID = "510811276"

logger = logging.getLogger(__name__)

async def send_renewal_success_notification(bot: Bot, order_details: dict):
    """
    Định dạng và gửi thông báo gia hạn thành công qua Telegram.
    """
    if not order_details:
        logger.warning("Hàm send_notification được gọi nhưng không có chi tiết đơn hàng.")
        return

    try:
        # --- Lấy và xử lý dữ liệu ---
        ma_don_hang = escape_mdv2(order_details.get('ID_DON_HANG'))
        san_pham = escape_mdv2(order_details.get('SAN_PHAM'))
        thong_tin_don = escape_mdv2(order_details.get('THONG_TIN_DON'))
        ngay_dang_ky = escape_mdv2(order_details.get('NGAY_DANG_KY'))
        ngay_het_han = escape_mdv2(order_details.get('HET_HAN'))
        gia_ban = format_currency(order_details.get('GIA_BAN'))
        nguon = escape_mdv2(order_details.get('NGUON'))
        gia_nhap = format_currency(order_details.get('GIA_NHAP'))

        slot_info = ""
        slot_data = order_details.get('SLOT')
        if slot_data and str(slot_data).strip():
            slot_info = f"\n📦 *Slot:* {escape_mdv2(slot_data)}"

        # --- Tạo tin nhắn với bố cục mới ---
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
        logging.info(f"Đã gửi thông báo gia hạn thành công cho mã {order_details.get('ID_DON_HANG')}")

    except Exception as e:
        logging.error(f"Lỗi khi gửi thông báo Telegram cho mã {order_details.get('ID_DON_HANG')}: {e}")