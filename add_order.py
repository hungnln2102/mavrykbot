import logging
import re
import asyncio
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from utils import connect_to_sheet, generate_unique_id, escape_mdv2
from menu import show_main_selector
from column import SHEETS, PRICE_COLUMNS, ORDER_COLUMNS
from collections import defaultdict


logger = logging.getLogger(__name__)

(STATE_CHON_LOAI_KHACH, STATE_NHAP_TEN_SP, STATE_CHON_MA_SP, STATE_NHAP_MA_MOI, 
 STATE_CHON_NGUON, STATE_NHAP_NGUON_MOI, STATE_NHAP_GIA_NHAP, STATE_NHAP_THONG_TIN, 
 STATE_NHAP_TEN_KHACH, STATE_NHAP_LINK_KHACH, STATE_NHAP_SLOT, 
 STATE_NHAP_GIA_BAN, STATE_NHAP_NOTE) = range(13)

# --- Các hàm tiện ích ---
def _col_letter(col_idx: int) -> str:
    """Chuyển đổi chỉ số cột (0=A, 1=B) thành ký tự cột trong Google Sheet."""
    if col_idx < 0:
        return ""
    letter = ""
    while col_idx >= 0:
        col_idx, remainder = divmod(col_idx, 26)
        letter = chr(65 + remainder) + letter
        col_idx -= 1
    return letter

def extract_days_from_ma_sp(ma_sp: str) -> int:
    match = re.search(r"--(\d+)m", ma_sp.lower())
    if match:
        thang = int(match.group(1))
        return 365 if thang == 12 else thang * 30
    return 0

def tinh_ngay_het_han(ngay_bat_dau_str, so_ngay_dang_ky):
    try:
        ngay_bat_dau = datetime.strptime(ngay_bat_dau_str, "%d/%m/%Y")
        
        tong_ngay = int(so_ngay_dang_ky)
        
        so_nam = tong_ngay // 365
        so_ngay_con_lai = tong_ngay % 365
        so_thang = so_ngay_con_lai // 30
        so_ngay_du = so_ngay_con_lai % 30
        
        ngay_het_han = ngay_bat_dau + relativedelta(
            years=so_nam,
            months=so_thang,
            days=so_ngay_du - 1
        )
        
        return ngay_het_han.strftime("%d/%m/%Y")
    except (ValueError, TypeError) as e:
        logger.error(f"[LỖI TÍNH NGÀY]: {e}")
        return ""

# --- Các hàm xử lý của Conversation ---

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['main_message_id'] = query.message.message_id

    keyboard = [
        [
            InlineKeyboardButton("Khách Lẻ", callback_data="le"),
            InlineKeyboardButton("Cộng Tác Viên", callback_data="ctv"),
        ],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")],
    ]

    await query.edit_message_text(
        "📦 *Khởi Tạo Đơn Hàng Mới*\n\nVui lòng lựa chọn phân loại khách hàng:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return STATE_CHON_LOAI_KHACH

async def chon_loai_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["loai_khach"] = query.data
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        ma_don = generate_unique_id(sheet, query.data)
        context.user_data["ma_don"] = ma_don
    except Exception as e:
        logger.error(f"Lỗi tạo mã đơn: {e}")
        await query.edit_message_text(escape_mdv2("❌ Lỗi kết nối Google Sheet."), parse_mode="MarkdownV2")
        return await end_add(update, context, success=False)

    ma_don_md = escape_mdv2(ma_don)
    message_text = f"🧾 Mã đơn: `{ma_don_md}`\n\n🏷️ Vui lòng nhập *Tên Sản Phẩm*:"
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]), parse_mode="MarkdownV2")
    return STATE_NHAP_TEN_SP

async def nhap_ten_sp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ten_sp = update.message.text.strip()
    await update.message.delete()
    context.user_data['ten_san_pham_raw'] = ten_sp
    main_message_id = context.user_data.get('main_message_id')
    chat_id = update.effective_chat.id
    
    ten_sp_md = escape_mdv2(ten_sp)
    text_part_1 = escape_mdv2("🔎 Đang tìm sản phẩm ")
    text_part_2 = escape_mdv2("...")
    await context.bot.edit_message_text(chat_id=chat_id, message_id=main_message_id, text=f"{text_part_1}*{ten_sp_md}*{text_part_2}", parse_mode="MarkdownV2")
    
    try:
        sheet_gia = connect_to_sheet().worksheet(SHEETS["PRICE"])
        price_data = sheet_gia.get_all_values()[1:]
        context.user_data['price_data_cache'] = price_data
    except Exception as e:
        logger.error(f"Lỗi khi tải bảng giá: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=main_message_id, text=escape_mdv2("❌ Lỗi kết nối Google Sheet."), parse_mode="MarkdownV2")
        return await end_add(update, context, success=False)

    grouped = defaultdict(list)
    for row in price_data:
        if len(row) > PRICE_COLUMNS["TEN_SAN_PHAM"] and ten_sp.lower() in row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip().lower():
            grouped[row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip()].append(row)

    if not grouped:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=main_message_id, text=f"❌ Không tìm thấy *{ten_sp_md}* trong bảng giá\\.\n\n✏️ Vui lòng nhập *Mã sản phẩm Mới*:", parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
        return STATE_NHAP_MA_MOI

    context.user_data['grouped_products'] = grouped
    
    # --- THAY ĐỔI LOGIC CHIA CỘT TẠI ĐÂY ---
    product_keys = list(grouped.keys())
    num_products = len(product_keys)
    num_columns = 3 if num_products > 9 else 2
    
    keyboard, row = [], []
    for ma_sp in product_keys:
        row.append(InlineKeyboardButton(text=ma_sp, callback_data=f"chon_ma|{ma_sp}"))
        if len(row) == num_columns:
            keyboard.append(row)
            row = []
    if row: 
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✏️ Nhập Mã Mới", callback_data="nhap_ma_moi"), InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")])
    
    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=main_message_id,
        text=f"📦 Vui lòng chọn *Mã sản phẩm* phù hợp cho *{ten_sp_md}*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="MarkdownV2"
    )
    return STATE_CHON_MA_SP

async def nhap_ma_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏️ Vui lòng nhập *Mã Sản Phẩm mới* (ví dụ: Netflix--1m):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_MA_MOI

async def xu_ly_ma_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ma_moi = update.message.text.strip().replace("—", "--").replace("–", "--")
    await update.message.delete()
    context.user_data['ma_chon'] = ma_moi
    so_ngay = extract_days_from_ma_sp(ma_moi)
    if so_ngay > 0: context.user_data['so_ngay'] = str(so_ngay)
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="🚚 Vui lòng nhập *tên Nguồn hàng mới*:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]), parse_mode="Markdown")
    return STATE_NHAP_NGUON_MOI
    
async def chon_ma_sp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ma_chon = query.data.split("|", 1)[1]
    context.user_data['ma_chon'] = ma_chon
    
    so_ngay = extract_days_from_ma_sp(ma_chon)
    if so_ngay > 0: context.user_data['so_ngay'] = str(so_ngay)
    
    ds = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    context.user_data['ds_san_pham_theo_ma'] = ds
    
    keyboard, row = [], []
    for r in ds:
        try:
            nguon, gia = r[PRICE_COLUMNS["NGUON"]].strip(), r[PRICE_COLUMNS["GIA_NHAP"]].strip()
            label = f"{nguon} - {gia}"
            row.append(InlineKeyboardButton(label, callback_data=f"chon_nguon|{nguon}"))
            if len(row) == 2: keyboard.append(row); row = []
        except IndexError: continue
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("➕ Nguồn Mới", callback_data="nguon_moi"), InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")])
    await query.edit_message_text(f"📦 Mã SP: `{escape_mdv2(ma_chon)}`\n\n🚚 Vui lòng chọn *Nguồn hàng*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")
    return STATE_CHON_NGUON

async def chon_nguon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    nguon = query.data.split("|", 1)[1]; context.user_data["nguon"] = nguon
    ds, loai_khach = context.user_data.get("ds_san_pham_theo_ma", []), context.user_data.get("loai_khach")
    gia_nhap, gia_ban = 0, 0
    for row in ds:
        if len(row) > PRICE_COLUMNS["NGUON"] and row[PRICE_COLUMNS["NGUON"]].strip() == nguon:
            try:
                gia_nhap_str = row[PRICE_COLUMNS["GIA_NHAP"]]
                gia_ban_col = PRICE_COLUMNS["GIA_BAN_CTV"] if loai_khach == "ctv" else PRICE_COLUMNS["GIA_BAN_LE"]
                gia_ban_str = row[gia_ban_col]
                gia_nhap = int(re.sub(r'[^\d]', '', gia_nhap_str))
                gia_ban = int(re.sub(r'[^\d]', '', gia_ban_str))
            except (ValueError, IndexError): gia_nhap, gia_ban = 0, 0
            break
    context.user_data["gia_nhap_value"], context.user_data["gia_ban_value"] = gia_nhap, gia_ban
    await query.edit_message_text("📝 Vui lòng nhập *Thông tin đơn hàng* (ví dụ: tài khoản, mật khẩu):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_THONG_TIN

async def chon_nguon_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    await query.edit_message_text("🚚 Vui lòng nhập *tên Nguồn hàng mới*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_NGUON_MOI

async def nhap_nguon_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nguon"] = update.message.text.strip(); await update.message.delete()
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="💰 Vui lòng nhập *Giá nhập*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_GIA_NHAP

async def nhap_gia_nhap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    gia_nhap_raw = update.message.text.strip(); await update.message.delete()
    try: context.user_data["gia_nhap_value"] = int(float(gia_nhap_raw.replace(",", ".")) * 1000)
    except ValueError:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="⚠️ Giá nhập không hợp lệ. Vui lòng nhập lại:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
        return STATE_NHAP_GIA_NHAP
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="📝 Vui lòng nhập *Thông tin đơn hàng*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_THONG_TIN

async def nhap_thong_tin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["thong_tin_don"] = update.message.text.strip(); await update.message.delete()
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="👤 Vui lòng nhập *tên khách hàng*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_TEN_KHACH

async def nhap_ten_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["khach_hang"] = update.message.text.strip(); await update.message.delete()
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_link")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="🔗 Vui lòng nhập *thông tin liên hệ* hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return STATE_NHAP_LINK_KHACH

async def nhap_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip: context.user_data["link_khach"] = ""; await query.answer()
    else: context.user_data["link_khach"] = update.message.text.strip(); await update.message.delete()
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_slot")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="🧩 Vui lòng nhập *Slot* (nếu có) hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return STATE_NHAP_SLOT

async def nhap_slot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip: context.user_data["slot"] = ""; await query.answer()
    else: context.user_data["slot"] = update.message.text.strip(); await update.message.delete()
    if "gia_ban_value" in context.user_data and context.user_data["gia_ban_value"] > 0:
        keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_note")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="📝 Vui lòng nhập *Ghi chú* (nếu có) hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return STATE_NHAP_NOTE
    else:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="💵 Vui lòng nhập *Giá bán*:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]), parse_mode="Markdown")
        return STATE_NHAP_GIA_BAN

async def nhap_gia_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    gia_ban_raw = update.message.text.strip(); await update.message.delete()
    try: context.user_data["gia_ban_value"] = int(float(gia_ban_raw.replace(",", ".")) * 1000)
    except ValueError:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="⚠️ Giá bán không hợp lệ. Vui lòng nhập lại:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]), parse_mode="Markdown")
        return STATE_NHAP_GIA_BAN
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_note")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text="📝 Vui lòng nhập *Ghi chú* (nếu có) hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return STATE_NHAP_NOTE

async def nhap_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip: context.user_data["note"] = ""; await query.answer()
    else: context.user_data["note"] = update.message.text.strip(); await update.message.delete()
    return await hoan_tat_don(update, context)

def tinh_ngay_het_han(ngay_bat_dau_str, so_ngay_dang_ky):
    """Sử dụng logic tính ngày chuẩn, có trừ 1 ngày."""
    try:
        from dateutil.relativedelta import relativedelta
        ngay_bat_dau = datetime.strptime(ngay_bat_dau_str, "%d/%m/%Y")
        
        tong_ngay = int(so_ngay_dang_ky)
        
        so_nam = tong_ngay // 365
        so_ngay_con_lai = tong_ngay % 365
        so_thang = so_ngay_con_lai // 30
        so_ngay_du = so_ngay_con_lai % 30
        
        ngay_het_han = ngay_bat_dau + relativedelta(
            years=so_nam,
            months=so_thang,
            days=so_ngay_du - 1
        )
        
        return ngay_het_han.strftime("%d/%m/%Y")
    except (ValueError, TypeError) as e:
        print(f"[LỖI TÍNH NGÀY]: {e}")
        return ""

async def end_add(update: Update, context: ContextTypes.DEFAULT_TYPE, success: bool = True) -> int:
    context.user_data.clear()
    return ConversationHandler.END

async def hoan_tat_don(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    chat_id = query.message.chat.id if query else update.effective_chat.id
    main_message_id = context.user_data.get('main_message_id')

    if main_message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=main_message_id,
            text="⏳ Đang hoàn tất đơn hàng, vui lòng chờ..."
        )
    try:
        info = context.user_data
        ngay_bat_dau_str = datetime.now().strftime("%d/%m/%Y")
        so_ngay = info.get("so_ngay", "0")
        gia_ban_value = info.get("gia_ban_value", 0)
        ngay_het_han = tinh_ngay_het_han(ngay_bat_dau_str, so_ngay)

        try:
            sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
            next_row = len(sheet.col_values(1)) + 1

            row_data = [""] * len(ORDER_COLUMNS)
            row_data[ORDER_COLUMNS["ID_DON_HANG"]]     = info.get("ma_don", "")
            row_data[ORDER_COLUMNS["SAN_PHAM"]]        = info.get("ma_chon", info.get("ten_san_pham_raw", ""))
            row_data[ORDER_COLUMNS["THONG_TIN_DON"]]   = info.get("thong_tin_don", "")
            row_data[ORDER_COLUMNS["TEN_KHACH"]]       = info.get("khach_hang", "")
            row_data[ORDER_COLUMNS["LINK_KHACH"]]      = info.get("link_khach", "")
            row_data[ORDER_COLUMNS["SLOT"]]            = info.get("slot", "")
            row_data[ORDER_COLUMNS["NGAY_DANG_KY"]]    = ngay_bat_dau_str
            row_data[ORDER_COLUMNS["SO_NGAY"]]         = so_ngay
            row_data[ORDER_COLUMNS["HET_HAN"]]         = ngay_het_han
            row_data[ORDER_COLUMNS["NGUON"]]           = info.get("nguon", "")
            row_data[ORDER_COLUMNS["GIA_NHAP"]]        = info.get("gia_nhap_value", "")
            row_data[ORDER_COLUMNS["GIA_BAN"]]         = gia_ban_value
            row_data[ORDER_COLUMNS["GHI_CHU"]]         = info.get("note", "")
            row_data[ORDER_COLUMNS["CHECK"]]           = "" 

            col_HH = _col_letter(ORDER_COLUMNS["HET_HAN"])
            col_CL = _col_letter(ORDER_COLUMNS["CON_LAI"])
            col_SN = _col_letter(ORDER_COLUMNS["SO_NGAY"])
            col_GB = _col_letter(ORDER_COLUMNS["GIA_BAN"])
            col_CK = _col_letter(ORDER_COLUMNS["CHECK"])

            row_data[ORDER_COLUMNS["CON_LAI"]] = f'=IF(ISBLANK({col_HH}{next_row}); ""; {col_HH}{next_row}-TODAY())'
            row_data[ORDER_COLUMNS["GIA_TRI_CON_LAI"]] = f'=IF(OR({col_SN}{next_row}="";{col_SN}{next_row}=0); 0; IFERROR({col_GB}{next_row}/{col_SN}{next_row}*{col_CL}{next_row}; 0))'
            row_data[ORDER_COLUMNS["TINH_TRANG"]] = f'=IF({col_CL}{next_row}<=0; "Hết Hạn"; IF({col_CK}{next_row}=TRUE; "Đã Thanh Toán"; "Chưa Thanh Toán"))'
            end_col_letter = _col_letter(len(ORDER_COLUMNS) - 1)
            sheet.update(f"A{next_row}:{end_col_letter}{next_row}", [row_data], value_input_option='USER_ENTERED')

        except Exception as e:
            error_message = escape_mdv2(f"❌ Lỗi khi ghi đơn hàng vào Google Sheet: {e}")
            await context.bot.edit_message_text(chat_id=chat_id, message_id=main_message_id, text=error_message, parse_mode="MarkdownV2")
            return await end_add(update, context, success=False)

        ma_don_final = info.get('ma_don','')
        qr_url = f"https://img.vietqr.io/image/VPB-9183400998-compact2.png?amount={gia_ban_value}&addInfo={requests.utils.quote(ma_don_final)}&accountName=NGO LE NGOC HUNG"

        caption = (
            f"✅ Đơn hàng `{escape_mdv2(ma_don_final)}` đã được tạo thành công\\!\n\n"
            f"📦 *THÔNG TIN SẢN PHẨM*\n"
            f"🔹 *Tên Sản Phẩm:* {escape_mdv2(info.get('ma_chon', ''))}\n"
            f"📝 *Thông Tin Đơn Hàng:* {escape_mdv2(info.get('thong_tin_don', ''))}\n"
            f"📆 *Ngày Bắt đầu:* {escape_mdv2(ngay_bat_dau_str)}\n"
            f"⏳ *Thời hạn:* {escape_mdv2(so_ngay)} ngày\n"
            f"📅 *Ngày Hết hạn:* {escape_mdv2(ngay_het_han)}\n"
            f"💵 *Giá bán:* {escape_mdv2(f'{gia_ban_value:,} đ')}\n\n"
            f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
            f"🔸 *Tên Khách Hàng:* {escape_mdv2(info.get('khach_hang', ''))}\n\n"
            f"📢 *HƯỚNG DẪN THANH TOÁN*\n"
            f"📢 *STK:* 9183400998\n"
            f"📢 *Nội dung:* Thanh toán `{escape_mdv2(ma_don_final)}`"
        )
        
        await context.bot.delete_message(chat_id=chat_id, message_id=main_message_id)
        await context.bot.send_photo(chat_id=chat_id, photo=qr_url, caption=caption, parse_mode="MarkdownV2")
        await show_main_selector(update, context, edit=False)

    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong hoan_tat_don: {e}")
        await context.bot.send_message(chat_id, f"Đã có lỗi xảy ra khi hoàn tất đơn: {e}")
    finally:
        return await end_add(update, context, success=True)

async def end_add(update: Update, context: ContextTypes.DEFAULT_TYPE, success: bool = True) -> int:
    query = update.callback_query
    context.user_data.clear()
    if not success:
        await asyncio.sleep(2)
        if query: await show_main_selector(update, context, edit=True)
    elif query:
        # Nếu thành công và bắt nguồn từ query, không cần làm gì thêm vì đã gửi ảnh mới
        pass
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(escape_mdv2("❌ Đã hủy thao tác thêm đơn."), parse_mode="MarkdownV2")
    return await end_add(update, context, success=False)

def get_add_order_conversation_handler():
    cancel_handler = CallbackQueryHandler(cancel_add, pattern="^cancel_add$")
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add$")],
        states={
            STATE_CHON_LOAI_KHACH: [cancel_handler, CallbackQueryHandler(chon_loai_khach_handler, pattern=r"^(le|ctv)$")],
            STATE_NHAP_TEN_SP: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_ten_sp_handler)],
            STATE_CHON_MA_SP: [cancel_handler, CallbackQueryHandler(chon_ma_sp_handler, pattern=r"^chon_ma\|"), CallbackQueryHandler(nhap_ma_moi_handler, pattern="^nhap_ma_moi$")],
            STATE_NHAP_MA_MOI: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, xu_ly_ma_moi_handler)],
            STATE_CHON_NGUON: [cancel_handler, CallbackQueryHandler(chon_nguon_handler, pattern=r"^chon_nguon\|"), CallbackQueryHandler(chon_nguon_moi_handler, pattern="^nguon_moi$")],
            STATE_NHAP_NGUON_MOI: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_nguon_moi_handler)],
            STATE_NHAP_GIA_NHAP: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_nhap_handler)],
            STATE_NHAP_THONG_TIN: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_thong_tin_handler)],
            STATE_NHAP_TEN_KHACH: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_ten_khach_handler)],
            STATE_NHAP_LINK_KHACH: [cancel_handler, CallbackQueryHandler(lambda u, c: nhap_link_khach_handler(u, c, skip=True), pattern="^skip_link$"), MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_link_khach_handler)],
            STATE_NHAP_SLOT: [cancel_handler, CallbackQueryHandler(lambda u, c: nhap_slot_handler(u, c, skip=True), pattern="^skip_slot$"), MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_slot_handler)],
            STATE_NHAP_GIA_BAN: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_ban_handler)],
            STATE_NHAP_NOTE: [cancel_handler, CallbackQueryHandler(lambda u, c: nhap_note_handler(u, c, skip=True), pattern="^skip_note$"), MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_note_handler)],
        },
        fallbacks=[cancel_handler],
        name="add_order_conversation",
        persistent=False,
        allow_reentry=True,
    )
