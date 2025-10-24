import logging
import re
import asyncio
from datetime import datetime, timedelta
import gspread
from update_states import *
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
# --- IMPORT TỪ UTILS VÀ CÁC FILE KHÁC ---
from utils import connect_to_sheet, escape_mdv2, chuan_hoa_gia
from menu import show_main_selector
from add_order import tinh_ngay_het_han
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX

# -----------------------------------------------------------------
# --- MỚI: IMPORT CÁC HÀM XỬ LÝ TỪ FOLDER 'update_handlers' ---
# -----------------------------------------------------------------
# Chúng ta sẽ tạo các file này ở bước tiếp theo
from update_handlers.simple import input_new_simple_value_handler
from update_handlers.san_pham import input_new_san_pham_handler
from update_handlers.nguon import input_new_nguon_handler
from update_handlers.ngay_dk import input_new_ngay_dk_handler
from update_handlers.so_ngay import input_new_so_ngay_handler
from update_handlers.ten_khach import (
    input_new_ten_khach_handler,
    input_new_link_khach_handler,
    skip_link_khach_handler
)
# -----------------------------------------------------------------

logger = logging.getLogger(__name__)

# --- TRẠNG THÁI (STATES) ---
(
    SELECT_MODE, INPUT_VALUE, SELECT_ACTION, EDIT_CHOOSE_FIELD,
    EDIT_INPUT_SIMPLE, EDIT_INPUT_SAN_PHAM, EDIT_INPUT_NGUON,
    EDIT_INPUT_NGAY_DK, EDIT_INPUT_SO_NGAY,
    EDIT_INPUT_TEN_KHACH, EDIT_INPUT_LINK_KHACH
) = range(11)


# --- CÁC HÀM HELPER (ĐƯỢC GIỮ LẠI VÌ DÙNG TRỰC TIẾP Ở FILE NÀY) ---

def normalize_product_duration(text: str) -> str:
    """Chuẩn hóa định dạng thời hạn sản phẩm (ví dụ: --12m)."""
    # Hàm này được giữ lại vì 'extend_order' cần dùng
    if not isinstance(text, str):
        text = str(text)
    s = re.sub(r"[\u2010-\u2015]", "-", text)
    s = re.sub(r"-+\s*(\d+)\s*m\b", r"--\1m", s, flags=re.I)
    return s

def format_order_message(row_data):
    """Tạo tin nhắn chi tiết đơn hàng từ dữ liệu hàng (row_data)."""
    # Hàm này được giữ lại vì 'show_matched_order' cần dùng
    def get_val(col_name):
        try:
            return str(row_data[ORDER_COLUMNS[col_name]]).strip()
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

# -----------------------------------------------------------------
# --- TOÀN BỘ LOGIC XỬ LÝ SỬA (input_new_... handler) ĐÃ ĐƯỢC DI CHUYỂN ---
# --- CÁC HÀM HELPER (_get_order_from_context, _update_gia_nhap, ...) ---
# --- CŨNG ĐÃ ĐƯỢC DI CHUYỂN SANG update_handlers/common.py ---
# -----------------------------------------------------------------


# --- CÁC HÀM XỬ LÝ (HANDLER) CHÍNH CỦA CONVERSATION ---

async def start_update_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bắt đầu Conversation, hỏi cách tra cứu (Mã đơn / Thông tin)."""
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
    """Lưu chế độ tra cứu và yêu cầu nhập giá trị."""
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
    """Tìm kiếm đơn hàng trong GSheet (Đã tối ưu hóa)."""
    search_term = update.message.text.strip() 
    
    await update.message.delete()

    main_message_id = context.user_data.get('main_message_id')
    chat_id = update.effective_chat.id
    check_mode = context.user_data.get("check_mode")

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=main_message_id,
        text="🔎 Đang tìm kiếm, vui lòng chờ...", reply_markup=None
    )

    matched = []
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])

        if check_mode == "mode_id":
            try:
                cell = sheet.find(search_term, in_column=ORDER_COLUMNS["ID_DON_HANG"] + 1)
                row_data = sheet.row_values(cell.row, value_render_option='FORMATTED_VALUE')
                matched.append({"data": row_data, "row_index": cell.row})
            except gspread.exceptions.CellNotFound:
                matched = []
            except Exception as e:
                logger.warning(f"Lỗi khi dùng sheet.find: {e}")
                matched = []

        elif check_mode == "mode_info":
            try:
                regex = re.compile(re.escape(search_term), re.IGNORECASE)
                cells = sheet.findall(regex, in_column=ORDER_COLUMNS['THONG_TIN_DON'] + 1)
                
                for cell in cells:
                    row_data = sheet.row_values(cell.row, value_render_option='FORMATTED_VALUE')
                    matched.append({"data": row_data, "row_index": cell.row})
            except Exception as e:
                logger.warning(f"Lỗi khi dùng sheet.findall: {e}")
                matched = []
        
        context.user_data.pop('order_sheet_cache', None) # Xóa cache lớn nếu có

    except Exception as e:
        logger.error(f"Lỗi kết nối Google Sheet khi tìm kiếm: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=main_message_id,
            text="❌ Lỗi kết nối Google Sheet."
        )
        return await end_update(update, context)

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
    """Hiển thị chi tiết đơn hàng tìm thấy và các nút hành động."""
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
    
    if index < 0: index = 0
    if index >= len(matched_orders): index = len(matched_orders) - 1
        
    context.user_data["current_match_index"] = index

    order_info = matched_orders[index]
    row_data = order_info["data"]
    ma_don = str(row_data[ORDER_COLUMNS["ID_DON_HANG"]])

    message_text = format_order_message(row_data) # Dùng hàm format đã giữ lại

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
    """Xử lý logic gia hạn đơn hàng (tăng ngày, cập nhật giá)."""
    query = update.callback_query
    await query.answer()
    ma_don = query.data.split("|")[1].strip()

    matched_orders = context.user_data.get("matched_orders", [])
    order_info = next((o for o in matched_orders
                       if str(o["data"][ORDER_COLUMNS["ID_DON_HANG"]]) == ma_don), None)
    if not order_info:
        await query.answer("Lỗi: Không tìm thấy đơn hàng trong cache!", show_alert=True)
        return await end_update(update, context)
    row_data, row_idx = order_info["data"], order_info["row_index"]

    san_pham = str(row_data[ORDER_COLUMNS["SAN_PHAM"]]).strip()
    nguon_hang = str(row_data[ORDER_COLUMNS["NGUON"]]).strip()
    ngay_cuoi_cu = str(row_data[ORDER_COLUMNS["HET_HAN"]]).strip()
    gia_nhap_cu = str(row_data[ORDER_COLUMNS["GIA_NHAP"]]).strip()
    gia_ban_cu = str(row_data[ORDER_COLUMNS["GIA_BAN"]]).strip()

    san_pham_norm = normalize_product_duration(san_pham) # Dùng hàm normalize đã giữ lại
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
        await query.answer(f"Lỗi: Ngày hết hạn cũ '{ngay_cuoi_cu}' không hợp lệ. Cần định dạng dd/mm/yyyy.", show_alert=True)
        return await end_update(update, context)

    gia_nhap_moi, gia_ban_moi = None, None
    try:
        sheet_ty_gia = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
        ty_gia_data = sheet_ty_gia.get_all_values(value_render_option='FORMATTED_VALUE')
        
        headers = ty_gia_data[0] if ty_gia_data else []
        is_ctv = ma_don.upper().startswith("MAVC")
        
        nguon_col_idx = -1
        for i, header_name in enumerate(headers):
            if str(header_name).strip().lower() == nguon_hang.strip().lower():
                nguon_col_idx = i
                break

        product_row = None
        for row in ty_gia_data[1:]:
            ten_sp_tygia = str(row[TYGIA_IDX["SAN_PHAM"]]) if len(row) > TYGIA_IDX["SAN_PHAM"] else ""
            if ten_sp_tygia.strip().lower() == san_pham.strip().lower():
                product_row = row
                break

        if product_row:
            gia_ban_col_idx = TYGIA_IDX["GIA_CTV"] if is_ctv else TYGIA_IDX["GIA_KHACH"]
            gia_ban_raw = str(product_row[gia_ban_col_idx]) if len(product_row) > gia_ban_col_idx else "0"
            _, gia_ban_moi = chuan_hoa_gia(gia_ban_raw) 

            if nguon_col_idx != -1 and len(product_row) > nguon_col_idx:
                gia_nhap_raw = str(product_row[nguon_col_idx])
                _, gia_nhap_moi = chuan_hoa_gia(gia_nhap_raw)

    except Exception as e:
        logger.warning(f"Không thể truy cập '{SHEETS['EXCHANGE']}': {e}. Sẽ dùng giá cũ.")

    final_gia_nhap = gia_nhap_moi if gia_nhap_moi is not None else chuan_hoa_gia(gia_nhap_cu)[1]
    final_gia_ban = gia_ban_moi if gia_ban_moi is not None else chuan_hoa_gia(gia_ban_cu)[1]

    try:
        ws = connect_to_sheet().worksheet(SHEETS["ORDER"])
        ws.update_cell(row_idx, ORDER_COLUMNS["NGAY_DANG_KY"] + 1, ngay_bat_dau_moi)
        ws.update_cell(row_idx, ORDER_COLUMNS["SO_NGAY"] + 1, so_ngay) 
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
    """Xử lý xóa đơn hàng."""
    query = update.callback_query
    await query.answer("Đang xóa...")
    ma_don_to_delete = query.data.split("|")[1].strip()
    matched_orders = context.user_data.get("matched_orders", [])
    order_info = next((o for o in matched_orders
                       if str(o["data"][ORDER_COLUMNS["ID_DON_HANG"]]) == ma_don_to_delete), None)
    if not order_info:
        await query.edit_message_text("❌ Lỗi: Không tìm thấy đơn hàng trong cache.")
        return await end_update(update, context)

    row_idx_to_delete = order_info["row_index"]

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        sheet.delete_rows(row_idx_to_delete)
        
        new_matched = [o for o in matched_orders if o['row_index'] != row_idx_to_delete]
        
        for order in new_matched:
            if order['row_index'] > row_idx_to_delete:
                order['row_index'] -= 1
                
        context.user_data['matched_orders'] = new_matched
        
        message = f"🗑️ Đơn hàng `{escape_mdv2(ma_don_to_delete)}` đã được xóa thành công\\!"
        
        if not new_matched:
            await query.edit_message_text(message, parse_mode="MarkdownV2", reply_markup=None)
            return await end_update(update, context)
        else:
            context.user_data['current_match_index'] = 0
            return await show_matched_order(update, context, success_notice="✅ Xóa thành công!")

    except Exception as e:
        logger.error(f"Lỗi khi xóa đơn {ma_don_to_delete}: {e}")
        await query.edit_message_text("❌ Lỗi khi cập nhật Google Sheet.")
    return await end_update(update, context)

async def start_edit_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hiển thị menu các trường cần sửa."""
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

async def choose_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Định tuyến (route) đến handler tương ứng với trường được chọn."""
    query = update.callback_query
    await query.answer()
    
    col_idx = int(query.data.split("_")[1])
    context.user_data['edit_col_idx'] = col_idx
    
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

    # --- LOGIC ĐỊNH TUYẾN TRUNG TÂM ---
    next_state = EDIT_INPUT_SIMPLE 
    
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
    
    await query.edit_message_text(
        f"✏️ Vui lòng nhập giá trị mới cho *{col_name}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return next_state

async def back_to_order_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Quay lại màn hình chi tiết đơn hàng (từ menu Sửa)."""
    # Hàm này gọi lại show_matched_order (đã có ở file này)
    return await show_matched_order(update, context)

async def end_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kết thúc Conversation và quay về menu chính."""
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
    """Hủy thao tác hiện tại và kết thúc Conversation."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Đã hủy thao tác.")
    return await end_update(update, context)


# --- ĐỊNH NGHĨA CONVERSATIONHANDLER ---

def get_update_order_conversation_handler():
    """Tạo và trả về ConversationHandler cho việc cập nhật đơn hàng."""
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
            
            # --- MỚI: Trỏ các state đến các hàm đã import ---
            EDIT_INPUT_SIMPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_new_simple_value_handler)],
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