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
from telegram.error import BadRequest
from utils import connect_to_sheet, generate_unique_id, escape_mdv2
from menu import show_main_selector
from column import SHEETS, ORDER_COLUMNS, TYGIA_IDX

logger = logging.getLogger(__name__)

# =============================
# Trạng thái Conversation
# =============================
(
    STATE_CHON_LOAI_KHACH, STATE_NHAP_TEN_SP, STATE_CHON_MA_SP, STATE_NHAP_MA_MOI,
    STATE_CHON_NGUON, STATE_NHAP_NGUON_MOI, STATE_NHAP_GIA_NHAP, STATE_NHAP_THONG_TIN,
    STATE_NHAP_TEN_KHACH, STATE_NHAP_LINK_KHACH, STATE_NHAP_SLOT,
    STATE_NHAP_GIA_BAN, STATE_NHAP_NOTE
) = range(13)

# =============================
# Tiện ích chung + MarkdownV2-safe
# =============================

def _col_letter(col_idx: int) -> str:
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


def to_int_vnd(s: str) -> int:
    """'1.200.000 đ' -> 1200000 ; '1200' -> 1200; '' -> 0"""
    if not s:
        return 0
    s = str(s).strip()
    # Xóa các ký tự tiền tệ và khoảng trắng
    s = s.replace("đ", "").replace("₫", "").replace(" ", "")
    # Xóa cả dấu chấm và dấu phẩy phân cách
    s = s.replace(",", "").replace(".", "") # <<< SỬA LỖI Ở ĐÂY
    
    # Chỉ lấy phần số
    m = re.findall(r"\d+", s)
    if not m:
        return 0
    try:
        return int(m[0])
    except Exception:
        return 0

# ---- MarkdownV2 helpers ----

def md(text: str) -> str:
    if text is None:
        return ""
    return escape_mdv2(str(text).replace("...", "…"))

async def safe_edit_md(bot, chat_id: int, message_id: int, text: str, reply_markup=None, try_plain: bool = True):
    try:
        return await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, reply_markup=reply_markup, parse_mode="MarkdownV2"
        )
    except BadRequest:
        if try_plain:
            return await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, reply_markup=reply_markup
            )
        raise

async def safe_send_md(bot, chat_id: int, text: str, reply_markup=None, try_plain: bool = True):
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=reply_markup, parse_mode="MarkdownV2"
        )
    except BadRequest:
        if try_plain:
            return await bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup
            )
        raise

def is_available(val) -> bool:
    s = str(val).strip().lower()
    return s in {
        "true", "1", "yes", "y", "x", "✓", "✔",
        "con", "còn", "còn hàng", "available", "stock", "ok"
    }

# =============================
# Entry
# =============================

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

    chat_id = query.message.chat.id
    await safe_edit_md(
        context.bot, chat_id, query.message.message_id,
        text="📦 *Khởi Tạo Đơn Hàng Mới*\n\nVui lòng lựa chọn phân loại khách hàng:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_CHON_LOAI_KHACH


async def chon_loai_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["loai_khach"] = query.data
    chat_id = query.message.chat.id

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        ma_don = generate_unique_id(sheet, query.data)
        context.user_data["ma_don"] = ma_don
    except Exception as e:
        logger.error(f"Lỗi tạo mã đơn: {e}")
        await safe_edit_md(context.bot, chat_id, query.message.message_id, md("❌ Lỗi kết nối Google Sheet."))
        return await end_add(update, context, success=False)

    text = f"🧾 Mã đơn: `{md(ma_don)}`\n\n🏷️ Vui lòng nhập *Tên Sản Phẩm*:"
    await safe_edit_md(
        context.bot, chat_id, query.message.message_id,
        text=text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_TEN_SP


# =============================
# 2) Nhập tên sản phẩm — đọc sheet "Tỷ giá"
# =============================
async def nhap_ten_sp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ten_sp = update.message.text.strip()
    await update.message.delete()
    context.user_data['ten_san_pham_raw'] = ten_sp
    main_message_id = context.user_data.get('main_message_id')
    chat_id = update.effective_chat.id

    await safe_edit_md(
        context.bot, chat_id, main_message_id,
        text=f"🔎 Đang tìm sản phẩm *{md(ten_sp)}*…"
    )

    try:
        ss = connect_to_sheet()
        sh = ss.worksheet(SHEETS["EXCHANGE"])  # 'Tỷ giá'
        all_vals = sh.get_all_values()
        headers = all_vals[0] if all_vals else []
        rows = all_vals[1:] if len(all_vals) > 1 else []
    except Exception as e:
        logger.error(f"Lỗi khi tải sheet Tỷ giá: {e}")
        await safe_edit_md(context.bot, chat_id, main_message_id, md("❌ Lỗi kết nối Google Sheet."))
        return await end_add(update, context, success=False)

    # C = Sản phẩm, F = Check/Còn hàng
    matched = []
    for r in rows:
        try:
            name = (r[TYGIA_IDX["SAN_PHAM"]] or "").strip()
            if ten_sp.lower() in name.lower():
                if is_available(r[TYGIA_IDX["STATUS"]] if len(r) > TYGIA_IDX["STATUS"] else ""):
                    matched.append(r)
        except Exception:
            continue

    # Không có mã còn hàng -> yêu cầu Nhập Mã mới + Nguồn mới (bỏ qua check Tỷ giá)
    if len(matched) < 1:
        context.user_data['skip_check_tygia'] = True
        await safe_edit_md(
            context.bot, chat_id, main_message_id,
            text=(
                "⚠️ Không có *mã sản phẩm còn hàng* trong *Tỷ giá*\n\n"
                "✏️ Vui lòng nhập *Mã sản phẩm mới* \\(ví dụ: `Netflix--1m`\\)\\."
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
        )
        return STATE_NHAP_MA_MOI

    # >= 1 mã → cho chọn mã (giá trị ở cột C)
    context.user_data["tygia_headers"] = headers
    context.user_data["tygia_rows_matched"] = matched

    product_keys = []
    for r in matched:
        val = (r[TYGIA_IDX["SAN_PHAM"]] or "").strip()
        if val and val not in product_keys:
            product_keys.append(val)

    num_columns = 3 if len(product_keys) > 9 else 2
    keyboard, row = [], []
    for ma_sp in product_keys:
        row.append(InlineKeyboardButton(text=ma_sp, callback_data=f"chon_ma|{ma_sp}"))
        if len(row) == num_columns:
            keyboard.append(row); row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("✏️ Nhập Mã Mới", callback_data="nhap_ma_moi"),
        InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")
    ])

    await safe_edit_md(
        context.bot, chat_id, main_message_id,
        text=f"📦 Vui lòng chọn *Mã sản phẩm* phù hợp cho *{md(ten_sp)}*:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_CHON_MA_SP


async def nhap_ma_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await safe_edit_md(
        context.bot, chat_id, query.message.message_id,
        text="✏️ Vui lòng nhập *Mã Sản Phẩm mới* \\(ví dụ: `Netflix--1m`\\)\\:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_MA_MOI


# Nếu không có mã hợp lệ trong Tỷ giá, sau khi nhập mã mới -> đi thẳng sang nhập Nguồn mới
async def xu_ly_ma_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ma_moi = update.message.text.strip().replace("—", "--").replace("–", "--")
    await update.message.delete()
    context.user_data['ma_chon'] = ma_moi
    so_ngay = extract_days_from_ma_sp(ma_moi)
    if so_ngay > 0:
        context.user_data['so_ngay'] = str(so_ngay)

    chat_id = update.effective_chat.id
    # nếu trước đó không có mã còn hàng -> bỏ qua check Tỷ giá, vào luôn nguồn mới
    await safe_edit_md(
        context.bot, chat_id, context.user_data['main_message_id'],
        text="🚚 Vui lòng nhập *tên Nguồn hàng mới*\\:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_NGUON_MOI


# =============================
# 3) Chọn mã -> liệt kê nguồn từ cột G→
# =============================
async def chon_ma_sp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ma_chon = query.data.split("|", 1)[1]
    context.user_data['ma_chon'] = ma_chon

    so_ngay = extract_days_from_ma_sp(ma_chon)
    if so_ngay > 0:
        context.user_data['so_ngay'] = str(so_ngay)

    headers = context.user_data.get("tygia_headers", [])
    rows = context.user_data.get("tygia_rows_matched", [])
    SRC_START = TYGIA_IDX["SRC_START"]

    # lấy đúng dòng sản phẩm
    product_row = None
    for r in rows:
        if (r[TYGIA_IDX["SAN_PHAM"]] or "").strip() == ma_chon:
            product_row = r
            break
    if not product_row:
        await safe_edit_md(context.bot, query.message.chat.id, query.message.message_id, md("❌ Không tìm thấy dòng sản phẩm trong cache."))
        return await end_add(update, context, success=False)

    context.user_data['product_row'] = product_row

    # liệt kê nguồn có giá trị ở G… (giá nhập)
    keyboard, row = [], []
    for col_idx in range(SRC_START, len(headers)):
        src_name = (headers[col_idx] or "").strip()
        val = (product_row[col_idx] or "").strip()
        if src_name and val:
            label = f"{src_name} - {val}"
            row.append(InlineKeyboardButton(label, callback_data=f"chon_nguon|{src_name}"))
            if len(row) == 2:
                keyboard.append(row); row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("➕ Nguồn Mới", callback_data="nguon_moi"), InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")])
    await safe_edit_md(
        context.bot, query.message.chat.id, query.message.message_id,
        text=f"📦 Mã SP: `{md(ma_chon)}`\n\n🚚 Vui lòng chọn *Nguồn hàng*:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_CHON_NGUON


# =============================
# 4) Chọn nguồn -> lấy Giá nhập (ô giao), Giá bán (D/E)
# =============================
async def chon_nguon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    # --- START OF FIX ---
    parts = query.data.split("|", 1)
    
    # Check if the split was successful and created at least two parts
    if len(parts) < 2:
        logger.warning(f"Received unexpected callback_data format in chon_nguon_handler: {query.data}")
        await query.edit_message_text("❌ Đã xảy ra lỗi, vui lòng thử lại từ đầu.")
        return await end_add(update, context, success=False)

    nguon = parts[1].strip()
    # --- END OF FIX ---

    context.user_data["nguon"] = nguon

    headers = context.user_data.get("tygia_headers", [])
    product_row = context.user_data.get("product_row", [])
    loai_khach = context.user_data.get("loai_khach")

    try:
        # giá nhập = ô (sản phẩm, nguồn)
        col_idx = headers.index(nguon)
        gia_nhap_cell = (product_row[col_idx] or "").strip()
        gia_nhap = to_int_vnd(gia_nhap_cell)

        # giá bán = D/E theo loại khách
        gia_ctv = to_int_vnd(product_row[TYGIA_IDX["GIA_CTV"]])    # D
        gia_khach = to_int_vnd(product_row[TYGIA_IDX["GIA_KHACH"]])  # E
        gia_ban = gia_ctv if loai_khach == "ctv" else gia_khach
    except Exception as e:
        logger.warning(f"Lỗi xác định giá theo Tỷ giá: {e}")
        gia_nhap, gia_ban = 0, 0

    # Số ngày từ hậu tố mã SP (ví dụ --1m)
    so_ngay = extract_days_from_ma_sp(context.user_data.get('ma_chon', ''))
    if so_ngay > 0:
        context.user_data['so_ngay'] = str(so_ngay)

    context.user_data["gia_nhap_value"] = gia_nhap
    context.user_data["gia_ban_value"] = gia_ban

    await query.edit_message_text("📝 Vui lòng nhập *Thông tin đơn hàng* (ví dụ: tài khoản, mật khẩu):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]))
    return STATE_NHAP_THONG_TIN


# =============================
# 5) Các bước còn lại giữ nguyên, nhưng dùng safe_edit_md/md
# =============================
async def chon_nguon_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit_md(
        context.bot, query.message.chat.id, query.message.message_id,
        text="🚚 Vui lòng nhập *tên Nguồn hàng mới*:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_NGUON_MOI


async def nhap_nguon_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nguon"] = update.message.text.strip()
    await update.message.delete()
    await safe_edit_md(
        context.bot, update.effective_chat.id, context.user_data['main_message_id'],
        text="💰 Vui lòng nhập *Giá nhập*:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_GIA_NHAP


# add_order.py

async def nhap_gia_nhap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    gia_nhap_raw = update.message.text.strip()
    await update.message.delete()
    
    clean = re.sub(r"[^\d]", "", gia_nhap_raw)

    if not clean:
        await safe_edit_md(
            context.bot, update.effective_chat.id, context.user_data['main_message_id'],
            text="⚠️ Giá nhập không hợp lệ. Vui lòng chỉ nhập số:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
        )
        return STATE_NHAP_GIA_NHAP

    gia_nhap_value = int(clean)
    
    # Sửa lại: Luôn nhân với 1000 nếu giá trị lớn hơn 0
    if gia_nhap_value > 0:
        gia_nhap_value *= 1000
    
    context.user_data["gia_nhap_value"] = gia_nhap_value

    await safe_edit_md(
        context.bot, update.effective_chat.id, context.user_data['main_message_id'],
        text="📝 Vui lòng nhập *Thông tin đơn hàng*:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_THONG_TIN

async def nhap_thong_tin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["thong_tin_don"] = update.message.text.strip()
    await update.message.delete()
    await safe_edit_md(
        context.bot, update.effective_chat.id, context.user_data['main_message_id'],
        text="👤 Vui lòng nhập *tên khách hàng*:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
    )
    return STATE_NHAP_TEN_KHACH


async def nhap_ten_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["khach_hang"] = update.message.text.strip()
    await update.message.delete()
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_link")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
    await safe_edit_md(
        context.bot, update.effective_chat.id, context.user_data['main_message_id'],
        text="🔗 Vui lòng nhập *thông tin liên hệ* hoặc bấm Bỏ Qua:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_NHAP_LINK_KHACH


async def nhap_link_khach_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip:
        context.user_data["link_khach"] = ""
        await query.answer()
        chat_id = query.message.chat.id
        mid = query.message.message_id
    else:
        context.user_data["link_khach"] = update.message.text.strip()
        await update.message.delete()
        chat_id = update.effective_chat.id
        mid = context.user_data['main_message_id']
    keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_slot")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
    await safe_edit_md(
        context.bot, chat_id, mid,
        text="🧩 Vui lòng nhập *Slot* \\(nếu có\\) hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_NHAP_SLOT


async def nhap_slot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip:
        context.user_data["slot"] = ""
        await query.answer()
        chat_id = query.message.chat.id
        mid = query.message.message_id
    else:
        context.user_data["slot"] = update.message.text.strip()
        await update.message.delete()
        chat_id = update.effective_chat.id
        mid = context.user_data['main_message_id']

    if "gia_ban_value" in context.user_data and context.user_data["gia_ban_value"] > 0:
        keyboard = [[InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_note")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]]
        await safe_edit_md(
            context.bot, chat_id, mid,
            text="📝 Vui lòng nhập *Ghi chú* \\(nếu có\\) hoặc bấm Bỏ Qua:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return STATE_NHAP_NOTE
    else:
        await safe_edit_md(
            context.bot, chat_id, mid,
            text="💵 Vui lòng nhập *Giá bán*:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
        )
        return STATE_NHAP_GIA_BAN


# add_order.py

async def nhap_gia_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    gia_ban_raw = update.message.text.strip()
    await update.message.delete()
    
    clean = re.sub(r"[^\d]", "", gia_ban_raw)

    if not clean:
        await safe_edit_md(
            context.bot, update.effective_chat.id, context.user_data['main_message_id'],
            text="⚠️ Giá bán không hợp lệ. Vui lòng chỉ nhập số:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]])
        )
        return STATE_NHAP_GIA_BAN

    gia_ban_value = int(clean)

    # Sửa lại: Luôn nhân với 1000 nếu giá trị lớn hơn 0
    if gia_ban_value > 0:
        gia_ban_value *= 1000

    context.user_data["gia_ban_value"] = gia_ban_value

    keyboard = [
        [InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="skip_note")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_add")]
    ]
    await safe_edit_md(
        context.bot, update.effective_chat.id, context.user_data['main_message_id'],
        text="📝 Vui lòng nhập *Ghi chú* (nếu có) hoặc bấm Bỏ Qua:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_NHAP_NOTE


async def nhap_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip:
        context.user_data["note"] = ""
        await query.answer()
    else:
        context.user_data["note"] = update.message.text.strip()
        await update.message.delete()
    return await hoan_tat_don(update, context)


# =============================
# Hoàn tất đơn & kết thúc
# =============================
async def hoan_tat_don(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    chat_id = query.message.chat.id if query else update.effective_chat.id
    main_message_id = context.user_data.get('main_message_id')

    if main_message_id:
        await safe_edit_md(
            context.bot, chat_id, main_message_id,
            text="⏳ Đang hoàn tất đơn hàng, vui lòng chờ…"
        )

    try:
        info = context.user_data
        ngay_bat_dau_str = datetime.now().strftime("%d/%m/%Y")
        so_ngay = info.get("so_ngay", "0")
        gia_ban_value = info.get("gia_ban_value", 0)
        ngay_het_han = tinh_ngay_het_han(ngay_bat_dau_str, so_ngay)

        # Ghi sheet
        try:
            sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
            next_row = len(sheet.col_values(1)) + 1

            row_data = [""] * len(ORDER_COLUMNS)
            row_data[ORDER_COLUMNS["ID_DON_HANG"]]   = info.get("ma_don", "")
            row_data[ORDER_COLUMNS["SAN_PHAM"]]      = info.get("ma_chon", info.get("ten_san_pham_raw", ""))
            row_data[ORDER_COLUMNS["THONG_TIN_DON"]] = info.get("thong_tin_don", "")
            row_data[ORDER_COLUMNS["TEN_KHACH"]]     = info.get("khach_hang", "")
            row_data[ORDER_COLUMNS["LINK_KHACH"]]    = info.get("link_khach", "")
            row_data[ORDER_COLUMNS["SLOT"]]          = info.get("slot", "")
            row_data[ORDER_COLUMNS["NGAY_DANG_KY"]]  = ngay_bat_dau_str
            row_data[ORDER_COLUMNS["SO_NGAY"]]       = so_ngay
            row_data[ORDER_COLUMNS["HET_HAN"]]       = ngay_het_han
            row_data[ORDER_COLUMNS["NGUON"]]         = info.get("nguon", "")
            row_data[ORDER_COLUMNS["GIA_NHAP"]]      = info.get("gia_nhap_value", "")
            row_data[ORDER_COLUMNS["GIA_BAN"]]       = gia_ban_value
            row_data[ORDER_COLUMNS["NOTE"]]          = info.get("note", "")
            row_data[ORDER_COLUMNS["CHECK"]]         = ""

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
            await safe_edit_md(context.bot, chat_id, main_message_id, md(f"❌ Lỗi khi ghi đơn hàng vào Google Sheet: {e}"))
            return await end_add(update, context, success=False)
        
        ma_don_final = info.get('ma_don','')
        caption = (
            f"✅ Đơn hàng `{escape_mdv2(ma_don_final)}` đã được tạo thành công\\!\n\n"
            f"📦 *THÔNG TIN SẢN PHẨM*\n"
            f"🔹 *Tên Sản Phẩm:* {escape_mdv2(info.get('ma_chon', ''))}\n"
            f"📝 *Thông Tin Đơn Hàng:* {escape_mdv2(info.get('thong_tin_don', ''))}\n"
            f"📆 *Ngày Bắt đầu:* {escape_mdv2(ngay_bat_dau_str)}\n"
            f"⏳ *Thời hạn:* {escape_mdv2(so_ngay)} ngày\n"
            f"📅 *Ngày Hết hạn:* {escape_mdv2(ngay_het_han)}\n"
            f"💵 *Giá bán:* {escape_mdv2(f'{gia_ban_value:,} đ')}\n\n"
            f" *━━━━━━ 👤 ━━━━━━*\n"
            f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
            f"🔸 *Tên Khách Hàng:* {escape_mdv2(info.get('khach_hang', ''))}\n\n"
            f" *━━━━━━ 💳 ━━━━━━*\n"
            f"📢 *HƯỚNG DẪN THANH TOÁN*\n"
            f"📢 *STK:* 9183400998\n"
            f"📢 *Nội dung:* Thanh toán `{escape_mdv2(ma_don_final)}`"
        )

        qr_url = (
            "https://img.vietqr.io/image/VPB-9183400998-compact2.png"
            f"?amount={gia_ban_value}&addInfo={requests.utils.quote(ma_don_final)}"
            "&accountName=NGO LE NGOC HUNG"
        )

        # xóa message chính và gửi ảnh QR
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=main_message_id)
        except Exception:
            pass
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=qr_url, caption=caption, parse_mode="MarkdownV2")
        except BadRequest:
            # fallback plain text nếu Telegram vẫn bắt lỗi
            await context.bot.send_photo(chat_id=chat_id, photo=qr_url, caption=caption)

        await show_main_selector(update, context, edit=False)

    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong hoan_tat_don: {e}")
        await safe_send_md(context.bot, chat_id, escape_mdv2(f"Đã có lỗi xảy ra khi hoàn tất đơn: {e}"))
    finally:
        return await end_add(update, context, success=True)

async def end_add(update: Update, context: ContextTypes.DEFAULT_TYPE, success: bool = True) -> int:
    query = update.callback_query
    context.user_data.clear()
    if not success and query:
        await asyncio.sleep(1)
        await show_main_selector(update, context, edit=True)
    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit_md(context.bot, query.message.chat.id, query.message.message_id, md("❌ Đã hủy thao tác thêm đơn."))
    return await end_add(update, context, success=False)


def get_add_order_conversation_handler():
    cancel_handler = CallbackQueryHandler(cancel_add, pattern="^cancel_add$")
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add$")],
        states={
            STATE_CHON_LOAI_KHACH: [cancel_handler, CallbackQueryHandler(chon_loai_khach_handler, pattern=r"^(le|ctv)$")],
            STATE_NHAP_TEN_SP: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_ten_sp_handler)],
            STATE_CHON_MA_SP: [cancel_handler, CallbackQueryHandler(chon_ma_sp_handler, pattern=r"^chon_ma\|"), CallbackQueryHandler(nhap_ma_moi_handler, pattern="^nhap_ma_moi$")],
            STATE_CHON_NGUON: [cancel_handler, CallbackQueryHandler(chon_nguon_handler, pattern=r"^chon_nguon\|"), CallbackQueryHandler(chon_nguon_moi_handler, pattern="^nguon_moi$")],
            STATE_NHAP_MA_MOI: [cancel_handler, MessageHandler(filters.TEXT & ~filters.COMMAND, xu_ly_ma_moi_handler)],
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
