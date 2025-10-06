# import_order.py
# Flow "Nhập Hàng" ghi vào sheet: Bảng Nhập Hàng
# - ID: MAVNxxxxx (unique giữa Bảng Đơn Hàng & Bảng Nhập Hàng)
# - Cấu trúc cột: theo IMPORT_COLUMNS trong column.py
# - Dùng helpers từ utils.py (gen_mavn_id, compute_dates, to_int, connect_to_sheet, escape_mdv2)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)
from column import SHEETS, IMPORT_COLUMNS
from utils import (
    gen_mavn_id, compute_dates, to_int,
    connect_to_sheet, escape_mdv2,
)
import logging

logger = logging.getLogger(__name__)

# =========================
# Conversation States
# =========================
ASK_PRODUCT, ASK_SOURCE, ASK_INFO, ASK_SLOT, ASK_PRICE, ASK_DAYS, CONFIRM = range(7)

def _col_letter(idx0: int) -> str:
    n = idx0 + 1
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

# =========================
# Entry
# =========================
async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu flow Nhập Hàng – sinh sẵn MAVNxxxxx và hỏi sản phẩm."""
    context.user_data.clear()
    context.user_data["flow"] = "nhap"
    context.user_data["ma_don"] = gen_mavn_id()

    kb = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")]]
    text = (
        "📦 *Nhập Hàng*\n"
        f"Mã phiếu: `{context.user_data['ma_don']}`\n\n"
        "👉 Nhập *tên/mã sản phẩm* (vd: `Adobe_80Gb_4PC_PR2-12m`)."
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            escape_mdv2(text), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await update.message.reply_text(
            escape_mdv2(text), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb)
        )
    return ASK_PRODUCT

# =========================
# Steps
# =========================
async def ask_product_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Vui lòng nhập *tên/mã sản phẩm*.", parse_mode="Markdown")
        return ASK_PRODUCT

    context.user_data["san_pham_raw"] = name

    kb = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")]]
    await update.message.reply_text(
        "Nguồn nhập là *ai*? (vd: *Ades*, *Bongmin*…)\n"
        "_Bạn có thể gõ tên mới nếu chưa có trong danh sách_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ASK_SOURCE


async def ask_source_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    src = (update.message.text or "").strip()
    if not src:
        await update.message.reply_text("Vui lòng nhập *Nguồn*.", parse_mode="Markdown")
        return ASK_SOURCE

    context.user_data["nguon"] = src

    kb = [[InlineKeyboardButton("Bỏ qua", callback_data="skip_info"),
           InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")]]
    await update.message.reply_text(
        "Nhập *Thông tin sản phẩm* (email/key/ghi chú…)\n"
        "→ hoặc bấm *Bỏ qua*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return ASK_INFO


async def skip_info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["thong_tin"] = ""
    return await _ask_slot(update, context)


async def ask_info_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["thong_tin"] = (update.message.text or "").strip()
    return await _ask_slot(update, context)


async def _ask_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Bỏ qua", callback_data="skip_slot"),
           InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")]]
    msg = "Nhập *Slot* (nếu có) → hoặc bấm *Bỏ qua*."
    if getattr(update, "message", None):
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ASK_SLOT


async def skip_slot_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["slot"] = ""
    return await _ask_price(update, context)


async def ask_slot_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["slot"] = (update.message.text or "").strip()
    return await _ask_price(update, context)


async def _ask_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")]]
    msg = "Nhập *Giá nhập* (vd: `850000` hoặc `850.000 đ`)."
    if getattr(update, "message", None):
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ASK_PRICE


async def ask_price_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gia = to_int(update.message.text, default=-1)
    if gia <= 0:
        await update.message.reply_text("Số tiền không hợp lệ, vui lòng nhập lại.")
        return ASK_PRICE

    context.user_data["gia_nhap_value"] = gia

    kb = [
        [InlineKeyboardButton("180 ngày", callback_data="days_180"),
         InlineKeyboardButton("365 ngày", callback_data="days_365")],
        [InlineKeyboardButton("Tự nhập", callback_data="days_custom")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")],
    ]
    await update.message.reply_text("Chọn *Số ngày* hoặc *Tự nhập*:", parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))
    return ASK_DAYS


async def choose_days_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    if data == "days_custom":
        await update.callback_query.edit_message_text("Nhập *Số ngày* (vd: 365):", parse_mode="Markdown")
        return ASK_DAYS

    # days_180 / days_365
    so_ngay = int(data.split("_")[1])
    context.user_data["so_ngay"] = so_ngay
    return await _confirm(update, context)


async def ask_days_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    so_ngay = to_int(update.message.text, default=0)
    if so_ngay <= 0:
        await update.message.reply_text("Vui lòng nhập *số ngày* hợp lệ.")
        return ASK_DAYS
    context.user_data["so_ngay"] = so_ngay
    return await _confirm(update, context)


async def _confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = context.user_data
    ngay_dk, het_han, con_lai = compute_dates(info["so_ngay"])
    info["ngay_dk"] = ngay_dk
    info["het_han"] = het_han
    info["con_lai"] = con_lai

    text = (
        "*Xác nhận Nhập Hàng*\n"
        f"• Mã: `{info['ma_don']}`\n"
        f"• Sản phẩm: {info['san_pham_raw']}\n"
        f"• Nguồn: {info['nguon']}\n"
        f"• Giá nhập: {info['gia_nhap_value']:,} đ\n"
        f"• Số ngày: {info['so_ngay']}  (Còn lại: {con_lai})\n"
        f"• Ngày ĐK → Hết hạn: {ngay_dk} → {het_han}\n"
        f"• Thông tin: {info.get('thong_tin','') or '(trống)'}\n"
        f"• Slot: {info.get('slot','') or '(trống)'}"
    )
    kb = [
        [InlineKeyboardButton("✅ Ghi vào Bảng Nhập Hàng", callback_data="confirm_import")],
        [InlineKeyboardButton("↩️ Sửa số ngày", callback_data="days_custom")],
        [InlineKeyboardButton("❌ Hủy", callback_data="cancel_import")],
    ]
    if getattr(update, "message", None):
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return CONFIRM


async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    info = context.user_data

    try:
        ss = connect_to_sheet()
        ws = ss.worksheet(SHEETS["IMPORT"])

        next_row = len(ws.col_values(1)) + 1
        row = [""] * len(IMPORT_COLUMNS)

        row[IMPORT_COLUMNS["ID_DON_HANG"]]      = info["ma_don"]
        row[IMPORT_COLUMNS["SAN_PHAM"]]         = info["san_pham_raw"]
        row[IMPORT_COLUMNS["THONG_TIN"]]        = info.get("thong_tin", "")
        row[IMPORT_COLUMNS["SLOT"]]             = info.get("slot", "")
        row[IMPORT_COLUMNS["NGAY_DANG_KY"]]     = info["ngay_dk"]
        row[IMPORT_COLUMNS["SO_NGAY"]]          = info["so_ngay"]
        row[IMPORT_COLUMNS["HET_HAN"]]          = info["het_han"]

        # ==== Công thức theo mapping, không hard-code H/I/J/M ====
        col_HET_HAN  = _col_letter(IMPORT_COLUMNS["HET_HAN"])
        col_CON_LAI  = _col_letter(IMPORT_COLUMNS["CON_LAI"])
        col_SO_NGAY  = _col_letter(IMPORT_COLUMNS["SO_NGAY"])
        col_GIA_NHAP = _col_letter(IMPORT_COLUMNS["GIA_NHAP"])
        col_CHECK    = _col_letter(IMPORT_COLUMNS["CHECK"])

        # Còn Lại = Hết Hạn - TODAY()
        row[IMPORT_COLUMNS["CON_LAI"]] = (
            f'=IF(ISBLANK({col_HET_HAN}{next_row}); ""; {col_HET_HAN}{next_row}-TODAY())'
        )

        row[IMPORT_COLUMNS["NGUON"]]            = info["nguon"]
        row[IMPORT_COLUMNS["GIA_NHAP"]]         = info["gia_nhap_value"]

        # Giá Trị Còn Lại = (Giá nhập / Số ngày) * Còn lại   ✅ FIX
        row[IMPORT_COLUMNS["GIA_TRI_CON_LAI"]]  = (
            f'=IF(OR({col_SO_NGAY}{next_row}="";{col_SO_NGAY}{next_row}=0); 0; '
            f'{col_GIA_NHAP}{next_row}/{col_SO_NGAY}{next_row}*{col_CON_LAI}{next_row})'
        )

        # Tình Trạng = IF(Còn Lại<=0; "Hết Hạn"; IF(Check=TRUE; "Đã Thanh Toán"; "Chưa Thanh Toán"))
        row[IMPORT_COLUMNS["TINH_TRANG"]] = (
            f'=IF({col_CON_LAI}{next_row}<=0; "Hết Hạn"; '
            f'IF({col_CHECK}{next_row}=TRUE; "Đã Thanh Toán"; "Chưa Thanh Toán"))'
        )

        row[IMPORT_COLUMNS["CHECK"]] = True

        end_col_letter = _col_letter(len(row) - 1)
        ws.update(
            f"A{next_row}:{end_col_letter}{next_row}",
            [row],
            value_input_option="USER_ENTERED",
        )
        await update.callback_query.edit_message_text("✅ Đã ghi vào *Bảng Nhập Hàng*.", parse_mode="Markdown")

    except Exception as e:
        logger.exception("Lỗi ghi Bảng Nhập Hàng: %s", e)
        await update.callback_query.edit_message_text("❌ Lỗi ghi Google Sheet.")
    return ConversationHandler.END

# =========================
# Cancel
# =========================
async def cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Đã hủy Nhập Hàng.")
    else:
        await update.message.reply_text("Đã hủy Nhập Hàng.")
    return ConversationHandler.END


# =========================
# Export handler
# =========================
def get_import_order_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_import, pattern=r"^nhap_hang$")],
        states={
            ASK_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_product_text)],
            ASK_SOURCE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_source_text)],
            ASK_INFO:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_info_text),
                CallbackQueryHandler(skip_info_cb, pattern=r"^skip_info$"),
            ],
            ASK_SLOT:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_slot_text),
                CallbackQueryHandler(skip_slot_cb, pattern=r"^skip_slot$"),
            ],
            ASK_PRICE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_price_text)],
            ASK_DAYS:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_days_text),
                CallbackQueryHandler(choose_days_cb, pattern=r"^(days_180|days_365|days_custom)$"),
            ],
            CONFIRM:     [
                CallbackQueryHandler(confirm_cb, pattern=r"^confirm_import$"),
                CallbackQueryHandler(choose_days_cb, pattern=r"^days_custom$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_cb, pattern=r"^cancel_import$")],
        name="import_order_flow",
        persistent=False,
    )
