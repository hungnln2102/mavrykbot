import logging
import re
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.helpers import escape_markdown
from utils import connect_to_sheet
from menu import show_main_selector
from add_order import tinh_ngay_het_han
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX

logger = logging.getLogger(__name__)

# Đã mở rộng các trạng thái (states) để xử lý logic chỉnh sửa phức tạp
(
    SELECT_MODE, INPUT_VALUE, SELECT_ACTION, EDIT_CHOOSE_FIELD,
    EDIT_INPUT_SIMPLE, EDIT_INPUT_SAN_PHAM, EDIT_INPUT_NGUON,
    EDIT_INPUT_NGAY_DK, EDIT_INPUT_SO_NGAY,
    EDIT_INPUT_TEN_KHACH, EDIT_INPUT_LINK_KHACH
) = range(11)

def escape_mdv2(text):
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', str(text))

def chuan_hoa_gia(text):
    try:
        s = str(text).lower().strip()
        is_thousand = 'k' in s
        digits = ''.join(filter(str.isdigit, s))
        if not digits:
            return "0", 0
        number = int(digits)
        if is_thousand:
            number *= 1000
        return "{:,}".format(number), number
    except (ValueError, TypeError):
        return "0", 0

def normalize_product_duration(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    s = re.sub(r"[\u2010-\u2015]", "-", text)
    s = re.sub(r"-+\s*(\d+)\s*m\b", r"--\1m", s, flags=re.I)
    return s

def format_order_message(row_data):
    def get_val(col_name):
        try:
            return row_data[ORDER_COLUMNS[col_name]].strip()
        except (IndexError, KeyError):
            return ""

    ma_don, san_pham, thong_tin, slot = get_val("ID_DON_HANG"), get_val("SAN_PHAM"), get_val("THONG_TIN_DON"), get_val("SLOT")
    ngay_dk, so_ngay, het_han, con_lai = get_val("NGAY_DANG_KY"), get_val("SO_NGAY"), get_val("HET_HAN"), get_val("CON_LAI")
    nguon, gia_nhap, gia_ban, gtcl = get_val("NGUON"), get_val("GIA_NHAP"), get_val("GIA_BAN"), get_val("GIA_TRI_CON_LAI")
    ten_khach, link_khach, note = get_val("TEN_KHACH"), get_val("LINK_KHACH"), get_val("NOTE")

    text = (
        f"✅ *CHI TIẾT ĐƠN HÀNG*\n"
        f"📦 Mã đơn: `{escape_mdv2(ma_don)}`\n\n"
        f"✧•══════•✧  SẢN PHẨM  ✧•══════•✧\n"
        f"🏷️ *Sản phẩm:* {escape_mdv2(san_pham)}\n"
        f"📝 *Thông Tin:* {escape_mdv2(thong_tin)}\n"
        + (f"🧙 *Slot:* {escape_mdv2(slot)}\n" if slot else "")
        + f"🗓️ *Ngày đăng ký:* {escape_mdv2(ngay_dk)}\n"
        f"📆 *Số ngày đăng ký:* {escape_mdv2(so_ngay)} ngày\n"
        f"⏳ *Hết hạn:* {escape_mdv2(het_han)}\n"
        f"📉 *Còn lại:* {escape_mdv2(con_lai)} ngày\n"
        f"🚚 *Nguồn hàng:* {escape_mdv2(nguon)}\n"
        f"📟 *Giá nhập:* {escape_mdv2(gia_nhap)}\n"
        f"💵 *Giá bán:* {escape_mdv2(gia_ban)}\n"
        f"💰 *Giá trị còn lại:* {escape_mdv2(gtcl)}\n"
        f"🗒️ *Ghi chú:* {escape_mdv2(note)}\n\n"
        f"✧•══════•✧  KHÁCH HÀNG  ✧•══════•✧\n"
        f"👤 *Tên:* {escape_mdv2(ten_khach)}\n"
        + (f"🔗 *Liên hệ:* {escape_mdv2(link_khach)}" if link_khach else "")
    )
    return text

async def start_update_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🔍 Mã Đơn", callback_data="mode_id"),
         InlineKeyboardButton("📝 Thông Tin SP", callback_data="mode_info")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "📋 Vui lòng chọn hình thức tra cứu đơn hàng:"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        context.user_data['main_message_id'] = update.callback_query.message.message_id
    else:
        msg = await update.message.reply_text(message_text, reply_markup=reply_markup)
        context.user_data['main_message_id'] = msg.message_id
    return SELECT_MODE

async def select_check_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['check_mode'] = query.data
    prompt = "🔢 Vui lòng nhập *mã đơn hàng*:" if query.data == "mode_id" \
        else "📝 Vui lòng nhập *thông tin sản phẩm* cần tìm:"
    await query.edit_message_text(
        prompt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
    )
    return INPUT_VALUE

async def input_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_term = update.message.text.strip().lower()
    await update.message.delete()

    main_message_id = context.user_data.get('main_message_id')
    chat_id = update.effective_chat.id
    check_mode = context.user_data.get("check_mode")

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=main_message_id,
        text="🔎 Đang tìm kiếm, vui lòng chờ...", reply_markup=None
    )

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        all_data = sheet.get_all_values()
        context.user_data['order_sheet_cache'] = all_data
    except Exception as e:
        logger.error(f"Lỗi khi tải dữ liệu từ sheet: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=main_message_id,
            text="❌ Lỗi kết nối Google Sheet."
        )
        return await end_update(update, context)

    matched = []
    if len(all_data) > 1:
        for i, row in enumerate(all_data[1:], start=2):
            if not any(cell.strip() for cell in row):
                continue
            if check_mode == "mode_id":
                if len(row) > ORDER_COLUMNS["ID_DON_HANG"] \
                        and row[ORDER_COLUMNS["ID_DON_HANG"]].strip().lower() == search_term:
                    matched.append({"data": row, "row_index": i})
                    break
            elif check_mode == "mode_info":
                if len(row) > ORDER_COLUMNS['THONG_TIN_DON'] \
                        and search_term in row[ORDER_COLUMNS['THONG_TIN_DON']].lower():
                    matched.append({"data": row, "row_index": i})

    if not matched:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=main_message_id,
            text="❌ Không tìm thấy đơn hàng nào phù hợp."
        )
        return await end_update(update, context)

    context.user_data['matched_orders'] = matched
    context.user_data['current_match_index'] = 0
    return await show_matched_order(update, context)

async def show_matched_order(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             direction: str = "stay", success_notice: str = None) -> int:
    query = update.callback_query
    if query:
        await query.answer()

    matched_orders = context.user_data.get("matched_orders", [])
    index = context.user_data.get("current_match_index", 0)
    main_message_id = context.user_data.get('main_message_id')
    chat_id = update.effective_chat.id

    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1
    context.user_data["current_match_index"] = index

    order_info = matched_orders[index]
    row_data = order_info["data"]
    ma_don = row_data[ORDER_COLUMNS["ID_DON_HANG"]]

    message_text = format_order_message(row_data)

    if success_notice:
        message_text = f"_{escape_mdv2(success_notice)}_\n\n{message_text}"

    buttons, nav_row = [], []
    if len(matched_orders) > 1:
        if index > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="nav_prev"))
        if index < len(matched_orders) - 1:
            nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="nav_next"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔁 Gia Hạn", callback_data=f"action_extend|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa", callback_data=f"action_delete|{ma_don}"),
        InlineKeyboardButton("✍️ Sửa", callback_data=f"action_edit|{ma_don}")
    ])
    buttons.append([InlineKeyboardButton("❌ Hủy & Quay lại Menu", callback_data="cancel_update")])

    if len(matched_orders) > 1:
        message_text += f"\n\n*Kết quả* `({index + 1}/{len(matched_orders)})`"

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=main_message_id,
        text=message_text, parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECT_ACTION

async def extend_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    matched_orders = context.user_data.get("matched_orders", [])
    order_info = next((o for o in matched_orders
                       if o["data"][ORDER_COLUMNS["ID_DON_HANG"]] == ma_don), None)
    if not order_info:
        await query.answer("Lỗi: Không tìm thấy đơn hàng trong cache!", show_alert=True)
        return await end_update(update, context)
    row_data, row_idx = order_info["data"], order_info["row_index"]

    san_pham = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
    nguon_hang = row_data[ORDER_COLUMNS["NGUON"]].strip()
    ngay_cuoi_cu = row_data[ORDER_COLUMNS["HET_HAN"]].strip()
    gia_nhap_cu = row_data[ORDER_COLUMNS["GIA_NHAP"]].strip()
    gia_ban_cu = row_data[ORDER_COLUMNS["GIA_BAN"]].strip()

    san_pham_norm = normalize_product_duration(san_pham)
    match_thoi_han = re.search(r"--\s*(\d+)\s*m", san_pham_norm, flags=re.I)
    if not match_thoi_han:
        await query.answer("Lỗi: Không thể xác định thời hạn từ tên sản phẩm (cần dạng '--12m').", show_alert=True)
        return await end_update(update, context)

    so_thang = int(match_thoi_han.group(1))
    so_ngay = 365 if so_thang == 12 else so_thang * 30

    try:
        start_dt = datetime.strptime(ngay_cuoi_cu, "%d/%m/%Y") + timedelta(days=1)
        ngay_bat_dau_moi = start_dt.strftime("%d/%m/%Y")
        ngay_het_han_moi = tinh_ngay_het_han(ngay_bat_dau_moi, str(so_ngay))
    except (ValueError, TypeError):
        await query.answer(f"Lỗi: Ngày hết hạn cũ '{ngay_cuoi_cu}' không hợp lệ.", show_alert=True)
        return await end_update(update, context)

    gia_nhap_moi, gia_ban_moi = None, None
    try:
        # Đổi sang dùng sheet "Tỷ Giá"
        sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
        ty_gia_data = sheet_ty_gia.get_all_values()
        
        headers = ty_gia_data[0] if ty_gia_data else []
        is_ctv = ma_don.upper().startswith("MAVC")
        
        # Tìm cột tương ứng với nguồn hàng của đơn
        nguon_col_idx = -1
        for i, header_name in enumerate(headers):
            if header_name.strip().lower() == nguon_hang.strip().lower():
                nguon_col_idx = i
                break

        # Tìm dòng tương ứng với sản phẩm
        product_row = None
        for row in ty_gia_data[1:]:
            ten_sp_tygia = row[TYGIA_IDX["SAN_PHAM"]] if len(row) > TYGIA_IDX["SAN_PHAM"] else ""
            if ten_sp_tygia.strip().lower() == san_pham.strip().lower():
                product_row = row
                break

        if product_row:
            # Lấy giá bán lẻ/CTV từ các cột cố định
            gia_ban_col_idx = TYGIA_IDX["GIA_CTV"] if is_ctv else TYGIA_IDX["GIA_KHACH"]
            gia_ban_raw = product_row[gia_ban_col_idx] if len(product_row) > gia_ban_col_idx else "0"
            _, gia_ban_moi = chuan_hoa_gia(gia_ban_raw)

            # Lấy giá nhập tại ô giao điểm (dòng sản phẩm, cột nguồn)
            if nguon_col_idx != -1 and len(product_row) > nguon_col_idx:
                gia_nhap_raw = product_row[nguon_col_idx]
                _, gia_nhap_moi = chuan_hoa_gia(gia_nhap_raw)

    except Exception as e:
        logger.warning(f"Không thể truy cập '{SHEETS['EXCHANGE']}': {e}. Sẽ dùng giá cũ.")

    final_gia_nhap = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
    final_gia_ban = gia_ban_moi if gia_ban_moi is not None else chuan_hoa_gia(gia_ban_cu)[1]

    try:
        ws = connect_to_sheet().worksheet(SHEETS["ORDER"])
        ws.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau_moi)
        ws.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, str(so_ngay))
        ws.update_cell(row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi)
        ws.update_cell(row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, final_gia_nhap)
        ws.update_cell(row_idx, ORDER_COLUMNS["GIA_BAN"] + 1, final_gia_ban)
        order_info['data'][ORDER_COLUMNS["NGAY_DANG_KY"]] = ngay_bat_dau_moi
        order_info['data'][ORDER_COLUMNS["SO_NGAY"]] = str(so_ngay)
        order_info['data'][ORDER_COLUMNS["HET_HAN"]] = ngay_het_han_moi
        order_info['data'][ORDER_COLUMNS["GIA_NHAP"]] = "{:,}".format(final_gia_nhap or 0)
        order_info['data'][ORDER_COLUMNS["GIA_BAN"]] = "{:,}".format(final_gia_ban or 0)
        await query.answer("✅ Gia hạn & cập nhật thành công!", show_alert=True)
        return await show_matched_order(update, context)
    except Exception as e:
        logger.error(f"Lỗi khi gia hạn đơn {ma_don}: {e}", exc_info=True)
        await query.answer("❌ Lỗi: Không thể cập nhật dữ liệu lên Google Sheet.", show_alert=True)
        return await end_update(update, context)

async def delete_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Đang xóa...")
    ma_don_to_delete = query.data.split("|")[1].strip()
    matched_orders = context.user_data.get("matched_orders", [])
    order_info = next((o for o in matched_orders
                       if o["data"][ORDER_COLUMNS["ID_DON_HANG"]] == ma_don_to_delete), None)
    if not order_info:
        await query.edit_message_text("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        return await end_update(update, context)

    row_idx_to_delete = order_info["row_index"]

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.delete_rows(row_idx_to_delete)
        all_data_cache = context.user_data.get('order_sheet_cache', [])
        all_data_cache.pop(row_idx_to_delete - 1)
        new_matched = []
        for order in matched_orders:
            if order['row_index'] == row_idx_to_delete:
                continue
            if order['row_index'] > row_idx_to_delete:
                order['row_index'] -= 1
            new_matched.append(order)
        context.user_data['matched_orders'] = new_matched
        message = f"🗑️ Đơn hàng `{escape_mdv2(ma_don_to_delete)}` đã được xóa thành công\\!"
        await query.edit_message_text(message, parse_mode="MarkdownV2", reply_markup=None)
    except Exception as e:
        logger.error(f"Lỗi khi xóa đơn {ma_don_to_delete}: {e}")
        await query.edit_message_text("❌ Lỗi khi cập nhật Google Sheet.")
    return await end_update(update, context)

# -----------------------------------------------------------------
# HÀM MỚI: Helper để lấy thông tin đơn hàng từ context
# -----------------------------------------------------------------
def _get_order_from_context(context: ContextTypes.DEFAULT_TYPE):
    """Helper to retrieve current order info from context."""
    ma_don = context.user_data.get('edit_ma_don')
    all_data_cache = context.user_data.get('order_sheet_cache', [])
    
    if not ma_don:
        return None, -1, None # ma_don, row_idx, row_data

    for i, item in enumerate(all_data_cache):
        if len(item) > ORDER_COLUMNS["ID_DON_HANG"] and item[ORDER_COLUMNS["ID_DON_HANG"]] == ma_don:
            # Trả về: mã đơn, chỉ số hàng (bắt đầu từ 1), dữ liệu hàng
            return ma_don, i + 1, item 
    
    return ma_don, -1, None # Không tìm thấy

# -----------------------------------------------------------------
# HÀM MỚI: Helper để cập nhật Giá Nhập
# -----------------------------------------------------------------
async def _update_gia_nhap(
    sheet_row_data: list, 
    sheet_row_idx: int, 
    ws: 'gspread.Worksheet' # 'gspread.Worksheet'
) -> (str, int):
    """
    Tự động cập nhật GIA_NHAP dựa trên SAN_PHAM và NGUON hiện tại của đơn hàng.
    Sử dụng logic tương tự như hàm extend_order.
    Trả về (giá_đã_format, giá_số)
    """
    try:
        san_pham = sheet_row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
        nguon_hang = sheet_row_data[ORDER_COLUMNS["NGUON"]].strip()
        gia_nhap_cu = sheet_row_data[ORDER_COLUMNS["GIA_NHAP"]].strip()
    except IndexError:
        logger.warning(f"Thiếu dữ liệu trong sheet_row_data để cập nhật giá nhập.")
        return "0", 0

    gia_nhap_moi = None
    try:
        sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
        ty_gia_data = sheet_ty_gia.get_all_values()
        
        headers = ty_gia_data[0] if ty_gia_data else []
        
        # Tìm cột tương ứng với nguồn hàng của đơn
        nguon_col_idx = -1
        for i, header_name in enumerate(headers):
            if header_name.strip().lower() == nguon_hang.strip().lower():
                nguon_col_idx = i
                break

        # Tìm dòng tương ứng với sản phẩm
        product_row = None
        for row in ty_gia_data[1:]:
            ten_sp_tygia = row[TYGIA_IDX["SAN_PHAM"]] if len(row) > TYGIA_IDX["SAN_PHAM"] else ""
            if ten_sp_tygia.strip().lower() == san_pham.strip().lower():
                product_row = row
                break

        # Lấy giá nhập tại ô giao điểm (dòng sản phẩm, cột nguồn)
        if product_row and nguon_col_idx != -1 and len(product_row) > nguon_col_idx:
            gia_nhap_raw = product_row[nguon_col_idx]
            _, gia_nhap_moi = chuan_hoa_gia(gia_nhap_raw)

    except Exception as e:
        logger.warning(f"Không thể truy cập '{SHEETS['EXCHANGE']}' để cập nhật giá nhập: {e}")

    final_gia_nhap_num = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
    final_gia_nhap_str = "{:,}".format(final_gia_nhap_num or 0)

    # Cập nhật GSheet và cache
    ws.update_cell(sheet_row_idx, ORDER_COLUMNS["GIA_NHAP"] + 1, final_gia_nhap_str)
    sheet_row_data[ORDER_COLUMNS["GIA_NHAP"]] = final_gia_nhap_str
    
    return final_gia_nhap_str, final_gia_nhap_num

# -----------------------------------------------------------------
# HÀM MỚI: Helper để cập nhật Ngày Hết Hạn
# -----------------------------------------------------------------
async def _update_het_han(
    sheet_row_data: list, 
    sheet_row_idx: int, 
    ws: 'gspread.Worksheet' # 'gspread.Worksheet'
) -> str:
    """
    Tự động cập nhật HET_HAN dựa trên NGAY_DANG_KY và SO_NGAY.
    Trả về ngày hết hạn mới (str).
    """
    try:
        ngay_dk = sheet_row_data[ORDER_COLUMNS["NGAY_DANG_KY"]].strip()
        so_ngay = sheet_row_data[ORDER_COLUMNS["SO_NGAY"]].strip()
        het_han_cu = sheet_row_data[ORDER_COLUMNS["HET_HAN"]].strip()
    except IndexError:
        logger.warning(f"Thiếu dữ liệu trong sheet_row_data để cập nhật ngày hết hạn.")
        return ""

    if not ngay_dk or not so_ngay:
        return het_han_cu # Trả về giá trị cũ nếu thiếu dữ liệu

    try:
        ngay_het_han_moi = tinh_ngay_het_han(ngay_dk, so_ngay)
    except (ValueError, TypeError):
        logger.warning(f"Không thể tính ngày hết hạn mới từ {ngay_dk} và {so_ngay}")
        return het_han_cu # Trả về giá trị cũ nếu lỗi

    # Cập nhật GSheet và cache
    ws.update_cell(sheet_row_idx, ORDER_COLUMNS["HET_HAN"] + 1, ngay_het_han_moi)
    sheet_row_data[ORDER_COLUMNS["HET_HAN"]] = ngay_het_han_moi
    
    return ngay_het_han_moi

# -----------------------------------------------------------------
# CẬP NHẬT: `start_edit_update` với nhiều nút hơn
# -----------------------------------------------------------------
async def start_edit_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()
    context.user_data['edit_ma_don'] = ma_don

    keyboard = [
        [
            InlineKeyboardButton("Sản phẩm", callback_data=f"edit_{ORDER_COLUMNS['SAN_PHAM']}"),
            InlineKeyboardButton("Thông Tin", callback_data=f"edit_{ORDER_COLUMNS['THONG_TIN_DON']}")
        ],
        [
            InlineKeyboardButton("Tên Khách", callback_data=f"edit_{ORDER_COLUMNS['TEN_KHACH']}"),
            InlineKeyboardButton("Link Khách", callback_data=f"edit_{ORDER_COLUMNS['LINK_KHACH']}")
        ],
        [
            InlineKeyboardButton("Slot", callback_data=f"edit_{ORDER_COLUMNS['SLOT']}"),
            InlineKeyboardButton("Nguồn", callback_data=f"edit_{ORDER_COLUMNS['NGUON']}")
        ],
        [
            InlineKeyboardButton("Ngày ĐK", callback_data=f"edit_{ORDER_COLUMNS['NGAY_DANG_KY']}"),
            InlineKeyboardButton("Số Ngày", callback_data=f"edit_{ORDER_COLUMNS['SO_NGAY']}")
        ],
        [
            InlineKeyboardButton("Giá Nhập", callback_data=f"edit_{ORDER_COLUMNS['GIA_NHAP']}"),
            InlineKeyboardButton("Giá Bán", callback_data=f"edit_{ORDER_COLUMNS['GIA_BAN']}")
        ],
        [
            InlineKeyboardButton("Ghi Chú", callback_data=f"edit_{ORDER_COLUMNS['NOTE']}"),
        ],
        [InlineKeyboardButton("Quay lại", callback_data="back_to_order")]
    ]

    await query.edit_message_text(
        "✍️ Vui lòng chọn trường cần chỉnh sửa:", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_CHOOSE_FIELD

# -----------------------------------------------------------------
# CẬP NHẬT: `choose_field_to_edit` để định tuyến (route)
# -----------------------------------------------------------------
async def choose_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    col_idx = int(query.data.split("_")[1])
    context.user_data['edit_col_idx'] = col_idx
    
    # Tìm tên cột để hiển thị prompt
    col_name = "Không xác định"
    for key, value in ORDER_COLUMNS.items():
        if value == col_idx:
            if key == 'THONG_TIN_DON': col_name = "Thông Tin SP"
            elif key == 'TEN_KHACH': col_name = "Tên Khách"
            elif key == 'LINK_KHACH': col_name = "Link Khách"
            elif key == 'NGAY_DANG_KY': col_name = "Ngày Đăng Ký"
            elif key == 'SO_NGAY': col_name = "Số Ngày"
            elif key == 'GIA_NHAP': col_name = "Giá Nhập"
            elif key == 'GIA_BAN': col_name = "Giá Bán"
            elif key == 'NOTE': col_name = "Ghi Chú"
            else: col_name = key.replace('_', ' ').title()
            break
            
    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Logic định tuyến: Quyết định trạng thái (state) tiếp theo
    next_state = EDIT_INPUT_SIMPLE # Mặc định cho các trường đơn giản
    
    if col_idx == ORDER_COLUMNS['SAN_PHAM']:
        next_state = EDIT_INPUT_SAN_PHAM
    elif col_idx == ORDER_COLUMNS['NGUON']:
        next_state = EDIT_INPUT_NGUON
    elif col_idx == ORDER_COLUMNS['NGAY_DANG_KY']:
        next_state = EDIT_INPUT_NGAY_DK
    elif col_idx == ORDER_COLUMNS['SO_NGAY']:
        next_state = EDIT_INPUT_SO_NGAY
    elif col_idx == ORDER_COLUMNS['TEN_KHACH']:
        next_state = EDIT_INPUT_TEN_KHACH
    
    # Các trường còn lại (GIA_BAN, GIA_NHAP, NOTE, SLOT, LINK_KHACH, THONG_TIN_DON)
    # sẽ dùng trạng thái mặc định: EDIT_INPUT_SIMPLE

    await query.edit_message_text(
        f"✏️ Vui lòng nhập giá trị mới cho *{col_name}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return next_state

# -----------------------------------------------------------------
# CẬP NHẬT: Đổi tên `input_new_value_handler` thành `input_new_simple_value_handler`
# -----------------------------------------------------------------
async def input_new_simple_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cập nhật giá trị mới (cho các trường đơn giản) vào sheet."""
    new_value_raw = update.message.text.strip()
    await update.message.delete()

    col_idx = context.user_data.get('edit_col_idx')
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)

    new_value_to_save = new_value_raw

    # Chuẩn hóa/Validate các trường đơn giản
    if col_idx in [ORDER_COLUMNS['GIA_BAN'], ORDER_COLUMNS['GIA_NHAP']]:
        gia_text, _ = chuan_hoa_gia(new_value_raw)
        if not gia_text or gia_text == "0":
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data.get('main_message_id'),
                text="⚠️ Giá không hợp lệ. Vui lòng nhập lại:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
            )
            return EDIT_INPUT_SIMPLE # Yêu cầu nhập lại
        new_value_to_save = gia_text
    
    # Ghi chú: Yêu cầu "Giá nhập: tự động thay đổi trong sheet tỷ giá"
    # rất phức tạp và có thể gây lỗi (ghi ngược).
    # Hiện tại, việc sửa Giá Nhập ở đây chỉ cập nhật trên sheet ORDER.
    # Giá Nhập sẽ tự động cập nhật nếu bạn sửa SẢN PHẨM hoặc NGUỒN.

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.update_cell(row_idx, col_idx + 1, new_value_to_save)
        original_row_data[col_idx] = new_value_to_save # Cập nhật cache
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật ô (simple): {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
    
    return await show_matched_order(update, context, success_notice="✅ Cập nhật thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật SẢN PHẨM (và Giá Nhập)
# -----------------------------------------------------------------
async def input_new_san_pham_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_value_raw = update.message.text.strip()
    await update.message.delete()
    
    col_idx = context.user_data.get('edit_col_idx') # Đây là ORDER_COLUMNS['SAN_PHAM']
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)

    new_san_pham = normalize_product_duration(new_value_raw)
    
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        
        # 1. Cập nhật SẢN PHẨM
        sheet.update_cell(row_idx, col_idx + 1, new_san_pham)
        original_row_data[col_idx] = new_san_pham # Cập nhật cache
        
        # 2. Kích hoạt cập nhật GIÁ NHẬP
        await _update_gia_nhap(original_row_data, row_idx, sheet)
        
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật SAN_PHAM: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
        
    return await show_matched_order(update, context, success_notice="✅ Cập nhật SẢN PHẨM & GIÁ NHẬP thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật NGUỒN (và Giá Nhập)
# -----------------------------------------------------------------
async def input_new_nguon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_nguon = update.message.text.strip()
    await update.message.delete()
    
    col_idx = context.user_data.get('edit_col_idx') # Đây là ORDER_COLUMNS['NGUON']
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        
        # 1. Cập nhật NGUỒN
        sheet.update_cell(row_idx, col_idx + 1, new_nguon)
        original_row_data[col_idx] = new_nguon # Cập nhật cache
        
        # 2. Kích hoạt cập nhật GIÁ NHẬP
        await _update_gia_nhap(original_row_data, row_idx, sheet)
        
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật NGUON: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
        
    return await show_matched_order(update, context, success_notice="✅ Cập nhật NGUỒN & GIÁ NHẬP thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật NGÀY ĐK (và Hết Hạn)
# -----------------------------------------------------------------
async def input_new_ngay_dk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_ngay_dk = update.message.text.strip()
    await update.message.delete()
    
    col_idx = context.user_data.get('edit_col_idx') # ORDER_COLUMNS['NGAY_DANG_KY']
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)

    # Validate định dạng ngày
    try:
        datetime.strptime(new_ngay_dk, "%d/%m/%Y")
    except ValueError:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text="⚠️ Định dạng ngày không hợp lệ (cần `dd/mm/yyyy`). Vui lòng nhập lại:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
        )
        return EDIT_INPUT_NGAY_DK # Yêu cầu nhập lại

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        
        # 1. Cập nhật NGÀY ĐĂNG KÝ
        sheet.update_cell(row_idx, col_idx + 1, new_ngay_dk)
        original_row_data[col_idx] = new_ngay_dk # Cập nhật cache
        
        # 2. Kích hoạt cập nhật HẾT HẠN
        await _update_het_han(original_row_data, row_idx, sheet)
        
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật NGAY_DANG_KY: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
        
    return await show_matched_order(update, context, success_notice="✅ Cập nhật NGÀY ĐK & HẾT HẠN thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật SỐ NGÀY (và Hết Hạn)
# -----------------------------------------------------------------
async def input_new_so_ngay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_so_ngay = update.message.text.strip()
    await update.message.delete()
    
    col_idx = context.user_data.get('edit_col_idx') # ORDER_COLUMNS['SO_NGAY']
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)

    # Validate số
    if not new_so_ngay.isdigit() or int(new_so_ngay) <= 0:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text="⚠️ Số ngày không hợp lệ (cần là một số > 0). Vui lòng nhập lại:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]])
        )
        return EDIT_INPUT_SO_NGAY # Yêu cầu nhập lại

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        
        # 1. Cập nhật SỐ NGÀY
        sheet.update_cell(row_idx, col_idx + 1, new_so_ngay)
        original_row_data[col_idx] = new_so_ngay # Cập nhật cache
        
        # 2. Kích hoạt cập nhật HẾT HẠN
        await _update_het_han(original_row_data, row_idx, sheet)
        
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật SO_NGAY: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
        
    return await show_matched_order(update, context, success_notice="✅ Cập nhật SỐ NGÀY & HẾT HẠN thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật TÊN KHÁCH (Bước 1/2)
# -----------------------------------------------------------------
async def input_new_ten_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_ten_khach = update.message.text.strip()
    await update.message.delete()
    
    col_idx = context.user_data.get('edit_col_idx') # ORDER_COLUMNS['TEN_KHACH']
    ma_don, row_idx, original_row_data = _get_order_from_context(context)

    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)
        
    try:
        # 1. Cập nhật TÊN KHÁCH ngay lập tức
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.update_cell(row_idx, col_idx + 1, new_ten_khach)
        original_row_data[col_idx] = new_ten_khach # Cập nhật cache
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật TEN_KHACH: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")

    # 2. Hỏi LINK KHÁCH
    keyboard = [
        [InlineKeyboardButton("Bỏ qua", callback_data="skip_link_khach")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_update")]
    ]
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text=f"✅ Đã cập nhật Tên Khách.\n\n🔗 Vui lòng nhập *Link Khách* (hoặc Bỏ qua):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_INPUT_LINK_KHACH # Chuyển sang trạng thái chờ nhập Link

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý cập nhật LINK KHÁCH (Bước 2/2)
# -----------------------------------------------------------------
async def input_new_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_link_khach = update.message.text.strip()
    await update.message.delete()
    
    col_idx = ORDER_COLUMNS['LINK_KHACH'] # Cố định cột Link Khách
    ma_don, row_idx, original_row_data = _get_order_from_context(context)
    
    if not original_row_data:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=context.user_data.get('main_message_id'),
            text=escape_mdv2("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        )
        return await end_update(update, context)
        
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.update_cell(row_idx, col_idx + 1, new_link_khach)
        original_row_data[col_idx] = new_link_khach # Cập nhật cache
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật LINK_KHACH: {e}")
        return await show_matched_order(update, context, success_notice="❌ Lỗi khi cập nhật Google Sheet.")
        
    return await show_matched_order(update, context, success_notice="✅ Cập nhật Tên Khách & Link Khách thành công!")

# -----------------------------------------------------------------
# HÀM MỚI: Xử lý Bỏ qua LINK KHÁCH (Bước 2/2)
# -----------------------------------------------------------------
async def skip_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Đã bỏ qua Link Khách")
    # Tên Khách đã được cập nhật ở bước trước, chỉ cần quay lại
    return await show_matched_order(update, context, success_notice="✅ Cập nhật Tên Khách thành công (bỏ qua link).")

async def back_to_order_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await show_matched_order(update, context)

async def end_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await asyncio.sleep(1)
    main_message_id = context.user_data.get('main_message_id')
    try:
        if update.callback_query:
            await show_main_selector(update, context, edit=True)
        else:
            if main_message_id:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=main_message_id)
            await show_main_selector(update, context, edit=False)
    except Exception as e:
        logger.warning(f"Không thể edit về menu chính, gửi mới: {e}")
        await show_main_selector(update, context, edit=False)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Đã hủy thao tác.")
    return await end_update(update, context)

# -----------------------------------------------------------------
# CẬP NHẬT: `get_update_order_conversation_handler` với các states mới
# -----------------------------------------------------------------
def get_update_order_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("update", start_update_order),
            CallbackQueryHandler(start_update_order, pattern="^update$")
        ],
        states={
            SELECT_MODE: [CallbackQueryHandler(select_check_mode, pattern="^mode_.*")],
            INPUT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_value_handler)],
            SELECT_ACTION: [
                CallbackQueryHandler(cancel_update, pattern="^cancel_update$"),
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "prev"), pattern="^nav_prev$"),
                CallbackQueryHandler(lambda u, c: show_matched_order(u, c, "next"), pattern="^nav_next$"),
                CallbackQueryHandler(extend_order, pattern="^action_extend\\|"),
                CallbackQueryHandler(delete_order, pattern="^action_delete\\|"),
                CallbackQueryHandler(start_edit_update, pattern="^action_edit\\|"),
            ],
            EDIT_CHOOSE_FIELD: [
                CallbackQueryHandler(choose_field_to_edit, pattern="^edit_.*"),
                CallbackQueryHandler(back_to_order_display, pattern="^back_to_order$"),
            ],
            # Trạng thái cho các trường đơn giản
            EDIT_INPUT_SIMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_simple_value_handler)],
            # Các trạng thái cho trường phức tạp
            EDIT_INPUT_SAN_PHAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_san_pham_handler)],
            EDIT_INPUT_NGUON: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_nguon_handler)],
            EDIT_INPUT_NGAY_DK: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_ngay_dk_handler)],
            EDIT_INPUT_SO_NGAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_so_ngay_handler)],
            EDIT_INPUT_TEN_KHACH: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_ten_khach_handler)],
            EDIT_INPUT_LINK_KHACH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_link_khach_handler),
                CallbackQueryHandler(skip_link_khach_handler, pattern="^skip_link_khach$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_update, pattern="^cancel_update$"),
            CommandHandler("cancel", cancel_update)
        ],
        name="update_order_conversation",
        persistent=False,
        allow_reentry=True
    )