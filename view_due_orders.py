# view_due_orders.py (Cập nhật: Dùng Job để gửi thông báo chi tiết)

import requests
import re
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from telegram.constants import ParseMode
from utils import connect_to_sheet, escape_mdv2
from io import BytesIO
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX
import logging
import asyncio
import config 

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# CÁC HÀM HỖ TRỢ (Khôi phục lại để dùng cho build_order_caption)
# --------------------------------------------------------------------

def clean_price_to_amount(text):
    """Chuyển đổi chuỗi giá thành số nguyên."""
    return int(str(text).replace(",", "").replace(".", "").replace("₫", "").replace("đ", "").replace(" ", ""))

def get_gia_ban(ma_don, ma_san_pham, banggia_data, gia_ban_donhang=None):
    """Lấy giá bán chính xác từ dữ liệu cache."""
    ma_sp = str(ma_san_pham).strip().replace("–", "--").replace("—", "--")
    is_ctv = str(ma_don).upper().startswith("MAVC")

    for row in banggia_data[1:]:
        if len(row) <= max(TYGIA_IDX["GIA_CTV"], TYGIA_IDX["GIA_KHACH"]): continue
        sp_goc = str(row[TYGIA_IDX["SAN_PHAM"]]).strip().replace("–", "--").replace("—", "--")
        if sp_goc == ma_sp:
            try:
                gia_str = row[TYGIA_IDX["GIA_CTV"]] if is_ctv else row[TYGIA_IDX["GIA_KHACH"]]
                gia = clean_price_to_amount(gia_str)
                if gia > 0: return gia
            except Exception as e:
                logger.warning(f"[Lỗi parse giá trong bảng giá]: {e}")
            break
    
    if isinstance(gia_ban_donhang, list): gia_ban_donhang = gia_ban_donhang[0] if gia_ban_donhang else ""
    return clean_price_to_amount(gia_ban_donhang) if gia_ban_donhang else 0

def build_order_caption(row: list, price_list_data: list, index: int, total: int):
    def get_val(col_name):
        # Hàm con helper để lấy dữ liệu an toàn
        try: return row[ORDER_COLUMNS[col_name]].strip()
        except (IndexError, KeyError): return ""
    
    ma_don_raw, product_raw = get_val("ID_DON_HANG"), get_val("SAN_PHAM")
    con_lai_raw = get_val("CON_LAI")
    
    days_left = int(float(con_lai_raw)) if con_lai_raw and con_lai_raw.replace('.', '', 1).isdigit() else 0
    gia_int = get_gia_ban(ma_don_raw, product_raw, price_list_data, row[ORDER_COLUMNS["GIA_BAN"]])
    gia_value_raw = "{:,} đ".format(gia_int) if gia_int > 0 else "Chưa xác định"

    product_md = escape_mdv2(product_raw)
    ma_don_md = escape_mdv2(ma_don_raw)
    info_md = escape_mdv2(get_val("THONG_TIN_DON"))
    ten_khach_md = escape_mdv2(get_val("TEN_KHACH"))
    link_khach_md = escape_mdv2(get_val("LINK_KHACH"))
    slot_md = escape_mdv2(get_val("SLOT"))
    ngay_dang_ky_md = escape_mdv2(get_val("NGAY_DANG_KY"))
    so_ngay_md = escape_mdv2(get_val("SO_NGAY"))
    ngay_het_han_md = escape_mdv2(get_val("HET_HAN"))
    gia_md = escape_mdv2(gia_value_raw)

    try:
        amount = clean_price_to_amount(gia_value_raw)
        qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={amount}&addInfo={ma_don_raw}&accountName=NGO%20LE%20NGOC%20HUNG"
        response = requests.get(qr_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        qr_image = BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi tạo QR: {e}")
        qr_image = None
        
    if days_left <= 0: status_line = f"⛔️ Đã hết hạn {abs(days_left)} ngày trước"
    else: status_line = f"⏳ Còn lại {days_left} ngày"
    
    header = (
        f"📦 *Đơn hàng đến hạn* `({index + 1}/{total})`\n"
        f"*{escape_mdv2('Sản phẩm:')}* {product_md}\n"
        f"*{escape_mdv2('Mã đơn:')}* `{ma_don_md}`\n"
        f"{escape_mdv2(status_line)}"
    )
    body = (
        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"📝 *Mô tả:* {info_md}\n" +
        (f"🧩 *Slot:* {slot_md}\n" if get_val("SLOT") else "") +
        (f"📅 Ngày đăng ký: {ngay_dang_ky_md}\n" if get_val("NGAY_DANG_KY") else "") +
        f"⏳ *Thời hạn:* {so_ngay_md} ngày\n"
        f"⏳ *Ngày hết hạn:* {ngay_het_han_md}\n"
        f"💵 *Giá bán:* {gia_md}\n\n"
        f"━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
        f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        f"🔸 *Tên:* {ten_khach_md}\n" +
        (f"🔗 *Liên hệ:* {link_khach_md}\n" if get_val("LINK_KHACH") else "")
    )
    footer = (
        escape_mdv2("━━━━━━━━━━━━━━━━━━━━━━\n") +
        escape_mdv2("💬 Để duy trì dịch vụ, quý khách vui lòng thanh toán theo thông tin dưới đây:\n\n") +
        escape_mdv2("🏦 Ngân hàng: VP Bank\n") +
        escape_mdv2("💳 STK: 9183400998\n") +
        escape_mdv2("👤 Tên: NGO LE NGOC HUNG\n") +
        escape_mdv2(f"📝 Nội dung: Thanh toán {ma_don_raw}\n\n") +
        escape_mdv2("📎 Vui lòng ghi đúng mã đơn hàng trong nội dung chuyển khoản để được xử lý nhanh chóng.\n") +
        escape_mdv2("✨ Trân trọng cảm ơn quý khách!\n") + "\u200b"
    )
    return f"{header}\n{escape_mdv2('━━━━━━━━━━━━━━━━━━━━━━')}\n{body}\n{footer}", qr_image

async def check_due_orders_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Chạy hàng ngày lúc 7:00 sáng, quét các đơn sắp hết hạn (CHÍNH XÁC = 4 ngày)
    và gửi thông báo chi tiết.
    """
    logger.info("Running daily due orders check job (logic == 4)...")
    
    try:
        spreadsheet = connect_to_sheet()
        order_sheet = spreadsheet.worksheet(SHEETS["ORDER"])
        price_sheet = spreadsheet.worksheet(SHEETS["EXCHANGE"])
        
        all_orders_data = order_sheet.get_all_values()
        price_list_data = price_sheet.get_all_values() # Cần cho hàm get_gia_ban
        
        if len(all_orders_data) <= 1:
            logger.info("Job: Không có dữ liệu đơn hàng nào.")
            return

    except Exception as e:
        logger.error(f"Job: Lỗi khi tải dữ liệu từ Google Sheet: {e}")
        return

    # Bước 1: Quét và thu thập các đơn hàng hợp lệ
    due_orders_info = []
    rows = all_orders_data[1:]
    
    for i, row in enumerate(rows, start=2):
        if not any(cell.strip() for cell in row): continue
        try:
            if len(row) <= ORDER_COLUMNS["CON_LAI"]: continue
            con_lai_val_str = row[ORDER_COLUMNS["CON_LAI"]].strip()
            if not con_lai_val_str: continue

            con_lai_val = int(float(con_lai_val_str))
            
            # === THAY ĐỔI QUAN TRỌNG: TỪ <= 4 THÀNH == 4 ===
            if con_lai_val == 4:
            # ============================================
                # Tìm thấy đơn, thêm vào danh sách để xử lý
                due_orders_info.append({"row_data": row})
                
        except (ValueError, IndexError, TypeError):
            continue

    # Bước 2: Gửi thông báo
    target_group_id = config.DUE_ORDER_GROUP_ID
    target_topic_id = config.DUE_ORDER_TOPIC_ID

    if not target_group_id or not target_topic_id:
        logger.error("Job: DUE_ORDER_GROUP_ID hoặc DUE_ORDER_TOPIC_ID chưa được cài đặt trong config!")
        return

    total_due = len(due_orders_info)
    if total_due == 0:
        logger.info("Job: Không có đơn hàng nào còn 4 ngày nữa hết hạn.")
        try:
            await context.bot.send_message(
                chat_id=target_group_id,
                message_thread_id=target_topic_id,
                text=escape_mdv2("✅ 7:00 Sáng: Không có đơn hàng nào còn đúng 4 ngày nữa hết hạn."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
             logger.error(f"Job: Không thể gửi thông báo 'không có đơn': {e}")
        return

    # Gửi tin nhắn thông báo bắt đầu
    await context.bot.send_message(
        chat_id=target_group_id,
        message_thread_id=target_topic_id,
        text=f"☀️ *THÔNG BÁO HẾT HẠN (7:00 Sáng)* ☀️\n\nPhát hiện *{total_due}* đơn hàng còn đúng 4 ngày nữa sẽ hết hạn:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    # Loop và gửi từng đơn hàng
    for index, order_info in enumerate(due_orders_info):
        try:
            caption, qr_image = build_order_caption(
                row=order_info["row_data"],
                price_list_data=price_list_data,
                index=index,
                total=total_due
            )
            
            if qr_image:
                qr_image.seek(0)
                await context.bot.send_photo(
                    chat_id=target_group_id,
                    message_thread_id=target_topic_id,
                    photo=qr_image,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await context.bot.send_message(
                    chat_id=target_group_id,
                    message_thread_id=target_topic_id,
                    text=caption,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            
            await asyncio.sleep(1.5) # Nghỉ để tránh spam/rate limit

        except Exception as e:
            logger.error(f"Job: Lỗi khi gửi chi tiết đơn hàng: {e}")
            await context.bot.send_message(
                chat_id=config.ERROR_GROUP_ID, # Gửi lỗi vào topic Lỗi
                message_thread_id=config.ERROR_TOPIC_ID,
                text=f"Job 'Đơn Hết Hạn' thất bại khi gửi 1 đơn:\n`{e}`"
            )

    logger.info(f"Job: Đã gửi xong {total_due} thông báo chi tiết.")