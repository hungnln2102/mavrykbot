# import_order.py — Dùng sheet "Tỷ giá" cho luồng Nhập Hàng
# - C: Sản Phẩm | D: Giá CTV | E: Giá Khách | F: Check/Còn hàng | G→: mỗi cột là 1 nguồn (ô = Giá nhập)
# - Chỉ xuất mã nếu F = TRUE
# - Nếu không còn mã nào sau lọc => yêu cầu nhập Mã SP mới & Nguồn mới (không check Tỷ giá)

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
from column import SHEETS, IMPORT_COLUMNS, TYGIA_IDX  # 👉 dùng TYGIA_IDX thay PRICE_COLUMNS
from menu import show_main_selector

logger = logging.getLogger(__name__)

(STATE_ASK_NAME, STATE_PICK_CODE, STATE_NEW_CODE, STATE_PICK_SOURCE,
 STATE_NEW_SOURCE, STATE_NHAP_GIA_NHAP_MOI, STATE_NHAP_THONG_TIN,
 STATE_NHAP_SLOT, STATE_CONFIRM) = range(9)

# ====== TIỆN ÍCH ======
def _col_letter(col_idx: int) -> str:
    """0->A, 1->B, ..."""
    if col_idx < 0:
        return ""
    letter = ""
    col_idx += 1
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

def extract_days_from_ma_sp(ma_sp: str) -> int:
    """Netflix--12m -> 365; --1m -> 30"""
    match = re.search(r"--(\d+)m", ma_sp.lower())
    if match:
        thang = int(match.group(1))
        return 365 if thang == 12 else thang * 30
    return 0

def tinh_ngay_het_han(ngay_bat_dau_str, so_ngay_dang_ky):
    """Tính ngày hết hạn (cộng năm/tháng/ngày và trừ 1 ngày ở phần days)."""
    try:
        from dateutil.relativedelta import relativedelta
        ngay_bat_dau = datetime.strptime(ngay_bat_dau_str, "%d/%m/%Y")
        tong_ngay = int(so_ngay_dang_ky)
        so_nam, so_ngay_con_lai = divmod(tong_ngay, 365)
        so_thang, so_ngay_du = divmod(so_ngay_con_lai, 30)
        ngay_het_han = ngay_bat_dau + relativedelta(
            years=so_nam, months=so_thang, days=so_ngay_du - 1
        )
        return ngay_het_han.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""

def to_int_vnd(s: str) -> int:
    """'1.200.000 đ' -> 1200000; '1200' -> 1200; '' -> 0"""
    if not s:
        return 0
    s = str(s).strip().replace("₫", "").replace("đ", "").replace(" ", "").replace(",", "")
    m = re.findall(r"\d+\.?\d*", s)
    if not m:
        return 0
    try:
        return int(float(m[0]))
    except Exception:
        return 0

def is_available(val) -> bool:
    """Cột F (Check/Còn hàng) => True nếu còn hàng."""
    s = str(val).strip().lower()
    return s in {
        "true", "1", "yes", "y", "x", "✓", "✔",
        "con", "còn", "còn hàng", "available", "stock", "ok"
    }

def kbd_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]])

def kbd_codes(cands: list[str]) -> InlineKeyboardMarkup:
    num_products = len(cands)
    num_columns = 3 if num_products > 9 else 2
    rows, row = [], []
    for name in cands:
        row.append(InlineKeyboardButton(name, callback_data=f"imp_code::{name}"))
        if len(row) == num_columns:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Nhập Mã Mới", callback_data="imp_new_code")])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="imp_cancel")])
    return InlineKeyboardMarkup(rows)

def kbd_sources(srcs: list[dict]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for source_info in srcs:
        try:
            price_val = to_int_vnd(source_info.get('price', '0'))
            price_display = f"{price_val:,}"
        except Exception:
            price_display = source_info.get('price', '0')
        source_name = source_info.get('name', 'N/A')
        label = f"{source_name} ({price_display}đ)"
        button = InlineKeyboardButton(label, callback_data=f"imp_src::{source_name}")
        row.append(button)
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("➕ Nguồn Mới", callback_data="imp_new_src")])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="imp_cancel")])
    return InlineKeyboardMarkup(rows)

def kbd_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Lưu Đơn Hàng", callback_data="imp_save")],
        [InlineKeyboardButton("✏️ Sửa Lại", callback_data="imp_edit")],
        [InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")],
    ])

# ====== LUỒNG CONVERSATION ======
async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['imp'] = {"voucher": gen_mavn_id()}
    context.user_data['main_message_id'] = query.message.message_id
    text = (
        "*📦 Nhập Đơn Hàng Mới*\n\n"
        f"Mã đơn hàng: `{escape_mdv2(context.user_data['imp']['voucher'])}`\n\n"
        "👉 Vui lòng nhập *tên hoặc mã sản phẩm* để tìm kiếm\\."
    )
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return STATE_ASK_NAME

def _get_exchange_data():
    """Đọc toàn bộ sheet 'Tỷ giá' và trả về headers + rows (bỏ header)."""
    try:
        sh = connect_to_sheet().worksheet(SHEETS["EXCHANGE"])
        all_vals = sh.get_all_values()
        headers = all_vals[0] if all_vals else []
        rows = all_vals[1:] if len(all_vals) > 1 else []
        return headers, rows
    except Exception as e:
        logger.error(f"Lỗi khi tải sheet Tỷ giá: {e}")
        return [], []

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Nhập tên SP -> lọc theo Cột C, chỉ giữ những dòng F=TRUE, sau đó cho chọn 'Mã sản phẩm' (C)."""
    name_query = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['name'] = name_query
    main_message_id = context.user_data.get('main_message_id')

    headers, rows = _get_exchange_data()
    if not headers:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=main_message_id,
            text=escape_mdv2("❌ Lỗi kết nối Google Sheet."),
            parse_mode="MarkdownV2"
        )
        return await on_cancel(update, context)

    # Lọc: tên chứa name_query (C) & chỉ lấy dòng còn hàng (F=TRUE)
    matched_rows = []
    for r in rows:
        try:
            name = (r[TYGIA_IDX["SAN_PHAM"]] or "").strip()
            if name_query.lower() in name.lower():
                if is_available(r[TYGIA_IDX["STATUS"]] if len(r) > TYGIA_IDX["STATUS"] else ""):
                    matched_rows.append(r)
        except Exception:
            continue

    if not matched_rows:
        # Không còn mã nào còn hàng -> yêu cầu nhập Mã SP mới & Nguồn mới (bỏ qua check Tỷ giá)
        context.user_data['imp']['skip_check_tygia'] = True
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=main_message_id,
            text=(
                f"❗Không tìm thấy *mã sản phẩm còn hàng* chứa `{escape_mdv2(name_query)}` trong *Tỷ giá*\\.\n\n"
                "✏️ Vui lòng nhập *Mã sản phẩm Mới* (ví dụ: `Netflix--1m`)\\:"
            ),
            parse_mode="MarkdownV2",
            reply_markup=kbd_cancel()
        )
        return STATE_NEW_CODE

    # Gom theo giá trị cột C (Sản phẩm)
    grouped = defaultdict(list)
    for r in matched_rows:
        key = (r[TYGIA_IDX["SAN_PHAM"]] or "").strip()
        if key:
            grouped[key].append(r)

    context.user_data['exchange_headers'] = headers
    context.user_data['grouped_products'] = grouped

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=main_message_id,
        text="🔎 Vui lòng chọn *sản phẩm* chính xác\\:",
        parse_mode="MarkdownV2",
        reply_markup=kbd_codes(list(grouped.keys()))
    )
    return STATE_PICK_CODE

async def on_pick_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chọn mã -> liệt kê nguồn từ G→; ô giao là Giá nhập."""
    query = update.callback_query
    await query.answer()

    if query.data == "imp_new_code":
        await query.message.edit_text(
            "✳️ Vui lòng nhập *mã sản phẩm mới* \\(ví dụ: Netflix--1m\\)\\:",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return STATE_NEW_CODE

    ma_chon = query.data.split("::", 1)[1]
    context.user_data['imp']['code'] = ma_chon
    so_ngay = extract_days_from_ma_sp(ma_chon)
    context.user_data['imp']['so_ngay'] = str(so_ngay) if so_ngay > 0 else "0"

    headers = context.user_data.get('exchange_headers', [])
    ds_rows = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    if not ds_rows:
        await query.message.edit_text("❌ Không tìm thấy dòng sản phẩm trong cache.", parse_mode="Markdown")
        return await on_cancel(update, context)

    # Chọn dòng đầu tiên cho mã (giả định theo cấu trúc sheet: cột G→ có các nguồn)
    product_row = ds_rows[0]
    context.user_data['imp']['product_row'] = product_row

    # Duyệt cột G→ để tạo danh sách nguồn có giá nhập
    sources = []
    for col_idx in range(TYGIA_IDX["SRC_START"], len(headers)):
        src_name = (headers[col_idx] or "").strip()
        val = (product_row[col_idx] or "").strip()
        if src_name and val:
            sources.append({'name': src_name, 'price': val})

    if not sources:
        # Không có nguồn có giá -> yêu cầu người dùng nhập nguồn mới
        await query.message.edit_text(
            "❗Sản phẩm này chưa có nguồn trong *Tỷ giá*\\. "
            "✳️ Vui lòng nhập *tên nguồn mới*\\:",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return STATE_NEW_SOURCE

    await query.message.edit_text(
        "🧭 Vui lòng chọn *Nguồn hàng*\\:",
        parse_mode="MarkdownV2",
        reply_markup=kbd_sources(sources)
    )
    return STATE_PICK_SOURCE

async def on_new_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mã mới -> nếu trước đó không có mã hợp lệ, bỏ qua kiểm tra Tỷ giá và vào nhập Nguồn mới."""
    code = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['code'] = code
    so_ngay = extract_days_from_ma_sp(code)
    context.user_data['imp']['so_ngay'] = str(so_ngay) if so_ngay > 0 else "0"

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text="✳️ Vui lòng nhập *tên nguồn hàng* cho sản phẩm mới này\\:",
        parse_mode="MarkdownV2",
        reply_markup=kbd_cancel()
    )
    return STATE_NEW_SOURCE

async def on_pick_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chọn nguồn có sẵn từ Tỷ giá => set Giá nhập từ ô giao. Hoặc chuyển sang Nguồn mới."""
    query = update.callback_query
    await query.answer()

    if query.data == "imp_new_src":
        await query.message.edit_text(
            "✳️ Vui lòng nhập *tên nguồn mới*\\:",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return STATE_NEW_SOURCE

    src = query.data.split("::", 1)[1]
    context.user_data['imp']['source'] = src

    headers = context.user_data.get('exchange_headers', [])
    product_row = context.user_data.get('imp', {}).get('product_row', [])
    try:
        col_idx = headers.index(src)
        cost_cell = (product_row[col_idx] or "").strip()
        gia_nhap = to_int_vnd(cost_cell)
    except Exception:
        gia_nhap = 0

    context.user_data['imp']['cost'] = gia_nhap

    await query.message.edit_text(
        "📝 Vui lòng nhập *Thông tin sản phẩm* \\(vd: tài khoản, mật khẩu\\)\\:",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_NHAP_THONG_TIN

async def on_new_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    src = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['source'] = src
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text="💰 Vui lòng nhập *Giá nhập* cho nguồn mới này\\:",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_NHAP_GIA_NHAP_MOI

async def nhap_gia_nhap_moi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['imp']['cost'] = to_int_vnd(update.message.text.strip())
    except Exception:
        await update.message.reply_text("Giá nhập không hợp lệ, vui lòng thử lại.")
        return STATE_NHAP_GIA_NHAP_MOI
    await update.message.delete()
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text="📝 Vui lòng nhập *Thông tin sản phẩm* \\(vd: tài khoản, mật khẩu\\)\\:",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_NHAP_THONG_TIN

async def nhap_thong_tin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['imp']['thong_tin_sp'] = update.message.text.strip()
    await update.message.delete()
    keyboard = [
        [InlineKeyboardButton("⏭️ Bỏ Qua", callback_data="imp_skip_slot")],
        [InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]
    ]
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text="🧩 Vui lòng nhập *Slot* \\(nếu có\\)\\:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2"
    )
    return STATE_NHAP_SLOT

async def nhap_slot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, skip: bool = False) -> int:
    query = update.callback_query
    if skip:
        context.user_data['imp']['slot'] = ""
        await query.answer()
    else:
        context.user_data['imp']['slot'] = update.message.text.strip()
        await update.message.delete()

    context.user_data['imp']['qty'] = "1"
    context.user_data['imp']['note'] = ""

    summary = fmt_summary(context.user_data['imp'])
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data.get('main_message_id'),
        text=summary, parse_mode="MarkdownV2",
        reply_markup=kbd_confirm()
    )
    return STATE_CONFIRM

def fmt_summary(d: dict) -> str:
    """Tóm tắt trước khi lưu."""
    gia_nhap_val = to_int_vnd(d.get('cost', 0))
    gia_nhap_str = f"{gia_nhap_val:,} đ" if gia_nhap_val > 0 else str(d.get('cost', '0'))
    so_ngay_str = d.get('so_ngay', '0')
    summary = (
        "*Xác nhận Đơn Hàng*\n\n"
        f"∙ *Mã Đơn Hàng*: `{escape_mdv2(d.get('voucher',''))}`\n"
        f"∙ *Sản Phẩm*: `{escape_mdv2(d.get('code',''))}`\n"
        f"∙ *Nguồn*: *{escape_mdv2(d.get('source',''))}*\n"
        f"∙ *Thông tin SP*: {escape_mdv2(d.get('thong_tin_sp',''))}\n"
        f"∙ *Slot*: {escape_mdv2(d.get('slot',''))}\n"
        f"∙ *Giá nhập*: *{escape_mdv2(gia_nhap_str)}*\n"
        f"∙ *Số lượng*: *1*\n"
    )
    if int(so_ngay_str) > 0:
        summary += f"∙ *Thời hạn*: *{escape_mdv2(so_ngay_str)} ngày*\n"
    return summary

async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "imp_edit":
        await query.message.edit_text("Vui lòng nhập lại *Thông tin sản phẩm*\\:", parse_mode="MarkdownV2")
        return STATE_NHAP_THONG_TIN

    if query.data == "imp_save":
        payload = context.user_data.get('imp', {})
        await query.edit_message_text(text="⏳ Đang lưu...")

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
            row_data[IMPORT_COLUMNS["GIA_NHAP"]] = to_int_vnd(payload.get("cost", 0))

            # Công thức
            col_CL = _col_letter(IMPORT_COLUMNS["CON_LAI"])
            col_HH = _col_letter(IMPORT_COLUMNS["HET_HAN"])
            col_SN = _col_letter(IMPORT_COLUMNS["SO_NGAY_DA_DANG_KY"])
            col_GN = _col_letter(IMPORT_COLUMNS["GIA_NHAP"])
            col_CK = _col_letter(IMPORT_COLUMNS["CHECK"])

            if int(so_ngay) > 0:
                row_data[IMPORT_COLUMNS["CON_LAI"]] = f'=IF(ISBLANK({col_HH}{next_row}); ""; {col_HH}{next_row}-TODAY())'
                row_data[IMPORT_COLUMNS["GIA_TRI_CON_LAI"]] = f'=IFERROR({col_GN}{next_row}/{col_SN}{next_row}*{col_CL}{next_row}; 0)'
                row_data[IMPORT_COLUMNS["TINH_TRANG"]] = f'=IF({col_CL}{next_row}<=0; "Hết Hạn"; IF({col_CK}{next_row}=TRUE; "Đã Thanh Toán"; "Chưa Thanh Toán"))'
            else:
                row_data[IMPORT_COLUMNS["TINH_TRANG"]] = "Không thời hạn"

            sheet.update(
                f"A{next_row}:{_col_letter(len(IMPORT_COLUMNS)-1)}{next_row}",
                [row_data], value_input_option='USER_ENTERED'
            )

            # ✅ FIX 1: Escaped the period for MarkdownV2
            await query.edit_message_text("✅ Đã lưu đơn hàng thành công\.", parse_mode="MarkdownV2")
            await show_main_selector(update, context, edit=False)

        except Exception as e:
            logger.exception("Lưu đơn hàng thất bại: %s", e)
            # ✅ FIX 2: Corrected the method name from edit_text to edit_message_text
            await query.edit_message_text(f"❌ Lỗi khi lưu: {escape_mdv2(str(e))}", parse_mode="MarkdownV2")

        context.user_data.clear()
        return ConversationHandler.END

    return await on_cancel(update, context)

async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Đã hủy thao tác.")
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
            STATE_NHAP_GIA_NHAP_MOI: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_nhap_moi_handler)],
            STATE_NHAP_THONG_TIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_thong_tin_handler)],
            STATE_NHAP_SLOT:   [
                CallbackQueryHandler(lambda u,c: nhap_slot_handler(u,c,skip=True), pattern='^imp_skip_slot$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_slot_handler)
            ],
            STATE_CONFIRM:     [CallbackQueryHandler(on_confirm, pattern=r'^(imp_save|imp_edit|imp_cancel)$')],
        },
        fallbacks=[CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
        name="import_order_conversation",
        persistent=False, allow_reentry=True,
    )
