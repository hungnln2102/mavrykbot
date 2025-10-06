# import_order.py (Phiên bản hoàn chỉnh)

import logging
import re
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from utils import connect_to_sheet, escape_mdv2, gen_mavn_id
from column import SHEETS, PRICE_COLUMNS, IMPORT_COLUMNS
from menu import show_main_selector

logger = logging.getLogger(__name__)

# Thêm các trạng thái mới cho luồng chi tiết
(STATE_ASK_NAME, STATE_PICK_CODE, STATE_NEW_CODE, STATE_PICK_SOURCE, 
 STATE_NEW_SOURCE, STATE_NHAP_THONG_TIN, STATE_NHAP_SLOT, STATE_ASK_DETAILS, 
 STATE_CONFIRM) = range(9)

# ====== CÁC HÀM TIỆN ÍCH ======
def _col_letter(col_idx: int) -> str:
    """Chuyển đổi chỉ số cột (0=A, 1=B...) thành ký tự cột trong Google Sheet."""
    if col_idx < 0: return ""
    letter = ""
    col_idx += 1
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

def extract_days_from_ma_sp(ma_sp: str) -> int:
    """Trích xuất số ngày từ mã sản phẩm (ví dụ: Netflix--12m -> 365)."""
    match = re.search(r"--(\d+)m", ma_sp.lower())
    if match:
        thang = int(match.group(1))
        return 365 if thang == 12 else thang * 30
    return 0

def tinh_ngay_het_han(ngay_bat_dau_str, so_ngay_dang_ky):
    """Tính ngày hết hạn từ ngày bắt đầu và số ngày."""
    try:
        from dateutil.relativedelta import relativedelta
        ngay_bat_dau = datetime.strptime(ngay_bat_dau_str, "%d/%m/%Y")
        tong_ngay = int(so_ngay_dang_ky)
        so_nam, so_ngay_con_lai = divmod(tong_ngay, 365)
        so_thang, so_ngay_du = divmod(so_ngay_con_lai, 30)
        ngay_het_han = ngay_bat_dau + relativedelta(years=so_nam, months=so_thang, days=so_ngay_du - 1)
        return ngay_het_han.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""

def fmt_summary(d: dict) -> str:
    """Định dạng tin nhắn tóm tắt thông tin nhập hàng."""
    gia_nhap_str = f"{int(d.get('cost', 0)):,} đ" if str(d.get('cost', '')).isdigit() else d.get('cost', '')
    so_ngay_str = d.get('so_ngay', '0')
    summary = (
        "*Xác nhận Nhập Hàng*\n\n"
        f"∙ *Mã Phiếu*: `{escape_mdv2(d.get('voucher',''))}`\n"
        f"∙ *Sản Phẩm*: `{escape_mdv2(d.get('code',''))}`\n"
        f"∙ *Nguồn*: *{escape_mdv2(d.get('source',''))}*\n"
        f"∙ *Thông tin SP*: {escape_mdv2(d.get('thong_tin_sp',''))}\n"
        f"∙ *Slot*: {escape_mdv2(d.get('slot',''))}\n"
        f"∙ *Giá nhập*: *{escape_mdv2(gia_nhap_str)}*\n"
        f"∙ *Số lượng*: *{escape_mdv2(str(d.get('qty','')))}*\n"
    )
    if int(so_ngay_str) > 0:
        summary += f"∙ *Thời hạn*: *{escape_mdv2(so_ngay_str)} ngày*\n"
    summary += f"∙ *Ghi chú*: {escape_mdv2(d.get('note',''))}"
    return summary

def get_price_data() -> list:
    """Lấy toàn bộ dữ liệu từ Bảng Giá."""
    try:
        sheet_gia = connect_to_sheet().worksheet(SHEETS["PRICE"])
        return sheet_gia.get_all_values()[1:]
    except Exception as e:
        logger.error(f"Lỗi khi tải bảng giá: {e}")
        return []

# ====== CÁC HÀM TẠO BÀN PHÍM (KEYBOARDS) ======
def kbd_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]])
def kbd_codes(cands: list[str]) -> InlineKeyboardMarkup:
    # --- THAY ĐỔI LOGIC CHIA CỘT TẠI ĐÂY ---
    num_products = len(cands)
    # Tự động quyết định số cột dựa trên số lượng sản phẩm
    num_columns = 3 if num_products > 9 else 2

    rows = []
    row = []
    for name in cands:
        button = InlineKeyboardButton(name, callback_data=f"imp_code::{name}")
        row.append(button)
        # Điều kiện chia cột được thay bằng biến động
        if len(row) == num_columns:
            rows.append(row)
            row = []
    
    # Thêm hàng cuối cùng nếu còn nút lẻ
    if row:
        rows.append(row)

    # Thêm các nút chức năng
    rows.append([InlineKeyboardButton("✏️ Nhập Mã Mới", callback_data="imp_new_code")])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="imp_cancel")])
    return InlineKeyboardMarkup(rows)
def kbd_sources(srcs: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for source_info in srcs:
        try:
            # Định dạng lại giá cho đẹp (vd: 850000 -> 850,000)
            price_val = int(re.sub(r'[^\d]', '', source_info.get('price', '0')))
            price_display = f"{price_val:,}"
        except (ValueError, TypeError):
            price_display = source_info.get('price', '0')

        source_name = source_info.get('name', 'N/A')
        label = f"{source_name} ({price_display}đ)"
        button = InlineKeyboardButton(label, callback_data=f"imp_src::{source_name}")
        
        row.append(button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Thêm các nút chức năng
    rows.append([InlineKeyboardButton("➕ Nguồn Mới", callback_data="imp_new_src")])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="imp_cancel")])
    return InlineKeyboardMarkup(rows)
def kbd_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Lưu Phiếu", callback_data="imp_save")],
        [InlineKeyboardButton("✏️ Sửa Lại", callback_data="imp_edit")],
        [InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")],
    ])

# ====== CÁC HÀM CỦA LUỒNG CONVERSATION ======
async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.user_data.clear()
    context.user_data['imp'] = {"voucher": gen_mavn_id()}
    context.user_data['main_message_id'] = query.message.message_id
    text = (
        "*📦 Nhập Hàng*\n\n"
        f"Mã phiếu: `{escape_mdv2(context.user_data['imp']['voucher'])}`\n\n"
        "👉 Vui lòng nhập *tên hoặc mã sản phẩm* để tìm kiếm\\."
    )
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return STATE_ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name_query = update.message.text.strip(); await update.message.delete()
    context.user_data['imp']['name'] = name_query
    main_message_id = context.user_data.get('main_message_id')
    price_data = get_price_data()
    if not price_data:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=main_message_id, text=escape_mdv2("❌ Lỗi kết nối Google Sheet."), parse_mode="MarkdownV2")
        return await on_cancel(update, context)
    grouped = defaultdict(list)
    for row in price_data:
        if len(row) > PRICE_COLUMNS["TEN_SAN_PHAM"] and name_query.lower() in row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip().lower():
            grouped[row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip()].append(row)
    context.user_data['price_data_cache'] = price_data
    context.user_data['grouped_products'] = grouped
    if not grouped:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=main_message_id, text=f"❗Không tìm thấy sản phẩm chứa *{escape_mdv2(name_query)}*\\. Vui lòng nhập *Mã sản phẩm mới*:", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return STATE_NEW_CODE
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=main_message_id, text="🔎 Vui lòng chọn *sản phẩm* chính xác:", parse_mode="MarkdownV2", reply_markup=kbd_codes(list(grouped.keys())))
    return STATE_PICK_CODE

async def on_pick_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "imp_new_code":
        await query.message.edit_text("✳️ Vui lòng nhập *mã sản phẩm mới* \\(ví dụ: Netflix--1m\\):", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return STATE_NEW_CODE
    
    ma_chon = query.data.split("::", 1)[1]
    context.user_data['imp']['code'] = ma_chon
    so_ngay = extract_days_from_ma_sp(ma_chon)
    context.user_data['imp']['so_ngay'] = str(so_ngay) if so_ngay > 0 else "0"
    
    ds_sp = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    context.user_data['imp']['ds_san_pham_theo_ma'] = ds_sp
    
    # Lấy nguồn và giá, loại bỏ trùng lặp
    sources_with_prices = {}
    for r in ds_sp:
        try:
            name = r[PRICE_COLUMNS["NGUON"]].strip()
            price_str = r[PRICE_COLUMNS["GIA_NHAP"]].strip()
            if name and name not in sources_with_prices:
                sources_with_prices[name] = price_str
        except IndexError:
            continue
    
    sources_list = [{'name': name, 'price': price} for name, price in sources_with_prices.items()]
    
    await query.message.edit_text("🧭 Vui lòng chọn *Nguồn hàng*:", parse_mode="MarkdownV2", reply_markup=kbd_sources(sources_list))
    return STATE_PICK_SOURCE

async def on_new_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip(); await update.message.delete()
    context.user_data['imp']['code'] = code
    so_ngay = extract_days_from_ma_sp(code)
    context.user_data['imp']['so_ngay'] = str(so_ngay) if so_ngay > 0 else "0"
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'), text="✳️ Vui lòng nhập *tên nguồn hàng* cho sản phẩm mới này:", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return STATE_NEW_SOURCE

async def on_pick_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "imp_new_src":
        await query.message.edit_text("✳️ Vui lòng nhập *tên nguồn mới*:", parse_mode="MarkdownV2", reply_markup=kbd_cancel()); return STATE_NEW_SOURCE
    src = query.data.split("::", 1)[1]
    context.user_data['imp']['source'] = src
    ds = context.user_data.get('imp', {}).get("ds_san_pham_theo_ma", [])
    gia_nhap = 0
    for row in ds:
        if len(row) > PRICE_COLUMNS["NGUON"] and row[PRICE_COLUMNS["NGUON"]].strip() == src:
            try: gia_nhap = int(re.sub(r'[^\d]', '', row[PRICE_COLUMNS["GIA_NHAP"]]))
            except (ValueError, IndexError): gia_nhap = 0
            break
    context.user_data['imp']['cost'] = gia_nhap
    
    # SỬA DÒNG DƯỚI ĐÂY
    await query.message.edit_text("📝 Vui lòng nhập *Thông tin sản phẩm* \\(vd: tài khoản, mật khẩu\\):", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    
    return STATE_NHAP_THONG_TIN

async def on_new_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    src = update.message.text.strip(); await update.message.delete()
    context.user_data['imp']['source'] = src
    
    # SỬA DÒNG DƯỚI ĐÂY
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, 
        message_id=context.user_data.get('main_message_id'), 
        text="📝 Vui lòng nhập *Thông tin sản phẩm* \\(vd: tài khoản, mật khẩu\\):", 
        parse_mode="MarkdownV2", 
        reply_markup=kbd_cancel()
    )
    
    return STATE_NHAP_THONG_TIN

async def nhap_thong_tin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['imp']['thong_tin_sp'] = update.message.text.strip(); await update.message.delete()
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="imp_skip_slot")], [InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]]
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'), text="🧩 Vui lòng nhập *Slot* (nếu có):", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")
    return STATE_NHAP_SLOT

async def nhap_slot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip:bool=False) -> int:
    query = update.callback_query
    if skip: context.user_data['imp']['slot'] = ""; await query.answer()
    else: context.user_data['imp']['slot'] = update.message.text.strip(); await update.message.delete()
    if 'cost' in context.user_data['imp']: prompt = "*Số lượng*`;` *Ghi chú \\(tùy chọn\\)*\n\n_Ví dụ_: `1; hàng có sẵn`"
    else: prompt = "*Giá nhập*`;` *Số lượng*`;` *Ghi chú \\(tùy chọn\\)*\n\n_Ví dụ_: `120000; 1; hàng có sẵn`"
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'), text=f"🧾 Nhập chi tiết cuối cùng:\n{prompt}", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return STATE_ASK_DETAILS

async def on_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip(); await update.message.delete()
    parts = [p.strip() for p in text.split(";")]
    if 'cost' in context.user_data['imp']:
        context.user_data['imp']['qty'] = parts[0] if parts else "1"
        context.user_data['imp']['note'] = parts[1] if len(parts) > 1 else ""
    else:
        context.user_data['imp']['cost'] = parts[0].replace('.', '').replace(',', '') if parts else "0"
        context.user_data['imp']['qty'] = parts[1] if len(parts) > 1 else "1"
        context.user_data['imp']['note'] = parts[2] if len(parts) > 2 else ""
    summary = fmt_summary(context.user_data['imp'])
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'), text=summary, parse_mode="MarkdownV2", reply_markup=kbd_confirm())
    return STATE_CONFIRM

async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "imp_edit":
        await query.message.edit_text("Vui lòng nhập lại chi tiết cuối cùng...", parse_mode="MarkdownV2")
        return STATE_ASK_DETAILS
    if query.data == "imp_save":
        payload = context.user_data.get('imp', {}); await query.edit_message_text(text="⏳ Đang lưu...")
        try:
            sheet = connect_to_sheet().worksheet(SHEETS["IMPORT"])
            next_row = len(sheet.col_values(1)) + 1
            ngay_bat_dau_str = datetime.now().strftime("%d/%m/%Y")
            so_ngay = payload.get("so_ngay", "0")
            ngay_het_han = tinh_ngay_het_han(ngay_bat_dau_str, so_ngay) if int(so_ngay) > 0 else ""
            
            row_data = [""] * len(IMPORT_COLUMNS)
            row_data[IMPORT_COLUMNS["ID_DON_HANG"]] = payload.get("voucher", "")
            row_data[IMPORT_COLUMNS["SAN_PHAM"]] = payload.get("code", "")
            row_data[IMPORT_COLUMNS["THONG_TIN_SAN_PHAM"]] = payload.get("thong_tin_sp", "")
            row_data[IMPORT_COLUMNS["SLOT"]] = payload.get("slot", "")
            row_data[IMPORT_COLUMNS["NGAY_DANG_KY"]] = ngay_bat_dau_str if int(so_ngay) > 0 else ""
            row_data[IMPORT_COLUMNS["SO_NGAY_DA_DANG_KY"]] = so_ngay if int(so_ngay) > 0 else ""
            row_data[IMPORT_COLUMNS["HET_HAN"]] = ngay_het_han
            row_data[IMPORT_COLUMNS["NGUON"]] = payload.get("source", "")
            row_data[IMPORT_COLUMNS["GIA_NHAP"]] = payload.get("cost", "")
            
            col_CL = _col_letter(IMPORT_COLUMNS["CON_LAI"])
            col_HH = _col_letter(IMPORT_COLUMNS["HET_HAN"])
            col_SN = _col_letter(IMPORT_COLUMNS["SO_NGAY_DA_DANG_KY"])
            col_GN = _col_letter(IMPORT_COLUMNS["GIA_NHAP"])
            
            if int(so_ngay) > 0:
                row_data[IMPORT_COLUMNS["CON_LAI"]] = f'=IF(ISBLANK({col_HH}{next_row}); ""; {col_HH}{next_row}-TODAY())'
                row_data[IMPORT_COLUMNS["GIA_TRI_CON_LAI"]] = f'=IFERROR({col_GN}{next_row}/{col_SN}{next_row}*{col_CL}{next_row}; 0)'
                row_data[IMPORT_COLUMNS["TINH_TRANG"]] = f'=IF({col_CL}{next_row}<=0; "Hết Hạn"; "Hoạt động")'
            else:
                row_data[IMPORT_COLUMNS["TINH_TRANG"]] = "Không thời hạn"
            row_data[IMPORT_COLUMNS["CHECK"]] = ""
            
            # Ghi dữ liệu vào sheet
            sheet.update(f"A{next_row}:{_col_letter(len(IMPORT_COLUMNS)-1)}{next_row}", [row_data], value_input_option='USER_ENTERED')
            await query.edit_message_text("✅ Đã lưu phiếu nhập hàng thành công\\.", parse_mode="MarkdownV2")
            await show_main_selector(update, context, edit=False)
        except Exception as e:
            logger.exception("Lưu phiếu nhập thất bại: %s", e)
            await query.edit_text(f"❌ Lỗi khi lưu: {escape_mdv2(str(e))}", parse_mode="MarkdownV2")
        context.user_data.clear()
        return ConversationHandler.END
    return await on_cancel(update, context)

async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer(); await query.edit_message_text("❌ Đã hủy thao tác.")
    context.user_data.clear()
    await show_main_selector(update, context, edit=False)
    return ConversationHandler.END

def get_import_order_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_import, pattern=r'^nhap_hang$')],
        states={
            STATE_ASK_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            STATE_PICK_CODE:   [CallbackQueryHandler(on_pick_code, pattern=r'^(imp_code::.+|imp_new_code)$')],
            STATE_NEW_CODE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_code)],
            STATE_PICK_SOURCE: [CallbackQueryHandler(on_pick_source, pattern=r'^(imp_src::.+|imp_new_src)$')],
            STATE_NEW_SOURCE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_source)],
            STATE_NHAP_THONG_TIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_thong_tin_handler)],
            STATE_NHAP_SLOT:   [CallbackQueryHandler(lambda u,c: nhap_slot_handler(u,c,skip=True), pattern='^imp_skip_slot$'),
                                MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_slot_handler)],
            STATE_ASK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_details)],
            STATE_CONFIRM:     [CallbackQueryHandler(on_confirm, pattern=r'^(imp_save|imp_edit|imp_cancel)$')],
        },
        fallbacks=[CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
        name="import_order_conversation",
        persistent=False, allow_reentry=True,
    )