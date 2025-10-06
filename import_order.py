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

# Import các thành phần dùng chung từ project của bạn
from utils import connect_to_sheet, escape_mdv2
from column import SHEETS, PRICE_COLUMNS, IMPORT_COLUMNS
from menu import show_main_selector

logger = logging.getLogger(__name__)

# ====== ĐỊNH NGHĨA CÁC TRẠNG THÁI (STATES) ======
(STATE_ASK_NAME, STATE_PICK_CODE, STATE_NEW_CODE, STATE_PICK_SOURCE, 
 STATE_NEW_SOURCE, STATE_ASK_DETAILS, STATE_CONFIRM) = range(7)


# ====== HÀM HỖ TRỢ ĐỊNH DẠNG VĂN BẢN ======
def fmt_summary(d: dict) -> str:
    """Định dạng tin nhắn tóm tắt thông tin nhập hàng."""
    gia_nhap_str = f"{int(d.get('cost', 0)):,} đ" if str(d.get('cost', '')).isdigit() else d.get('cost', '')
    return (
        "*Xác nhận Nhập Hàng*\n\n"
        f"∙ *Mã phiếu*: `{escape_mdv2(d.get('voucher',''))}`\n"
        f"∙ *Tên SP tìm kiếm*: *{escape_mdv2(d.get('name',''))}*\n"
        f"∙ *Mã SP đã chọn*: `{escape_mdv2(d.get('code',''))}`\n"
        f"∙ *Nguồn hàng*: *{escape_mdv2(d.get('source',''))}*\n"
        f"∙ *Số lượng*: *{escape_mdv2(str(d.get('qty','')))}*\n"
        f"∙ *Giá nhập / đơn vị*: *{escape_mdv2(gia_nhap_str)}*\n"
        f"∙ *Ghi chú*: {escape_mdv2(d.get('note',''))}"
    )

# ====== HÀM HỖ TRỢ DỮ LIỆU ======
def gen_voucher_no(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Tạo mã phiếu nhập hàng độc nhất."""
    n = context.application.bot_data.get("imp_counter", 0) + 1
    context.application.bot_data["imp_counter"] = n
    return f"NH{datetime.now().strftime('%y%m%d')}{n:04d}"

def get_price_data() -> list:
    """Lấy toàn bộ dữ liệu từ Bảng Giá."""
    try:
        sheet_gia = connect_to_sheet().worksheet(SHEETS["PRICE"])
        return sheet_gia.get_all_values()[1:]
    except Exception as e:
        logger.error(f"Lỗi khi tải bảng giá: {e}")
        return []

# ====== HÀM TẠO BÀN PHÍM (KEYBOARDS) ======
def kbd_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]])

def kbd_codes(cands: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"imp_code::{name}")] for name in cands]
    rows.append([InlineKeyboardButton("✏️ Nhập Mã Mới", callback_data="imp_new_code")])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="imp_cancel")])
    return InlineKeyboardMarkup(rows)

def kbd_sources(srcs: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(s, callback_data=f"imp_src::{s}")] for s in srcs]
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
    """Bắt đầu luồng nhập hàng."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    context.user_data['imp'] = {"voucher": gen_voucher_no(context)}
    context.user_data['main_message_id'] = query.message.message_id

    text = (
        "*📦 Nhập Hàng*\n\n"
        f"Mã phiếu: `{escape_mdv2(context.user_data['imp']['voucher'])}`\n\n"
        "👉 Vui lòng nhập *tên hoặc mã sản phẩm* để tìm kiếm\\."
    )
    
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return STATE_ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý tên sản phẩm người dùng nhập."""
    name_query = update.message.text.strip()
    await update.message.delete()
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
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=main_message_id,
            text=f"❗Không tìm thấy sản phẩm chứa *{escape_mdv2(name_query)}*\\. Vui lòng nhập *Mã sản phẩm mới*:",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return STATE_NEW_CODE

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=main_message_id,
        text="🔎 Vui lòng chọn *sản phẩm* chính xác:",
        parse_mode="MarkdownV2",
        reply_markup=kbd_codes(list(grouped.keys()))
    )
    return STATE_PICK_CODE

async def on_pick_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng chọn một sản phẩm từ danh sách."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "imp_new_code":
        await query.message.edit_text("✳️ Vui lòng nhập *mã sản phẩm mới* \\(ví dụ: Netflix-1m\\):", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return STATE_NEW_CODE
    
    ma_chon = query.data.split("::", 1)[1]
    context.user_data['imp']['code'] = ma_chon

    ds_sp = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    sources = sorted(list(set(r[PRICE_COLUMNS["NGUON"]].strip() for r in ds_sp if len(r) > PRICE_COLUMNS["NGUON"] and r[PRICE_COLUMNS["NGUON"]].strip())))

    await query.message.edit_text("🧭 Vui lòng chọn *Nguồn hàng*:", parse_mode="MarkdownV2", reply_markup=kbd_sources(sources))
    return STATE_PICK_SOURCE

async def on_new_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng tự nhập một mã sản phẩm mới."""
    code = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['code'] = code
    
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'),
        text="✳️ Vui lòng nhập *tên nguồn hàng* cho sản phẩm mới này:",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_NEW_SOURCE

async def on_pick_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng chọn một nguồn hàng từ bàn phím."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "imp_new_src":
        await query.message.edit_text("✳️ Vui lòng nhập *tên nguồn mới*:", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return STATE_NEW_SOURCE
        
    src = query.data.split("::", 1)[1]
    context.user_data['imp']['source'] = src
    
    await query.message.edit_text(
        "🧾 Nhập chi tiết theo định dạng:\n"
        "*Số lượng*`;` *Giá nhập*`;` *Ghi chú \\(tùy chọn\\)*\n\n"
        "_Ví dụ_: `5; 120000; hàng mới về`",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_ASK_DETAILS

async def on_new_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng nhập một nguồn hàng mới."""
    src = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['source'] = src
    
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'),
        text=(
            "🧾 Nhập chi tiết theo định dạng:\n"
            "*Số lượng*`;` *Giá nhập*`;` *Ghi chú \\(tùy chọn\\)*\n\n"
            "_Ví dụ_: `5; 120000; hàng mới về`"
        ),
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return STATE_ASK_DETAILS

async def on_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý khi người dùng nhập chi tiết Số lượng; Giá nhập; Ghi chú."""
    text = update.message.text.strip()
    await update.message.delete()
    
    parts = [p.strip() for p in text.split(";")]
    context.user_data['imp']['qty'] = parts[0] if parts else ""
    context.user_data['imp']['cost'] = parts[1].replace('.', '').replace(',', '') if len(parts) > 1 else ""
    context.user_data['imp']['note'] = parts[2] if len(parts) > 2 else ""

    summary = fmt_summary(context.user_data['imp'])
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data.get('main_message_id'),
        text=summary, parse_mode="MarkdownV2", reply_markup=kbd_confirm()
    )
    return STATE_CONFIRM

async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xử lý xác nhận cuối cùng: Lưu, Sửa, hoặc Hủy."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "imp_edit":
        await query.message.edit_text(
            "🧾 Vui lòng nhập lại chi tiết:\n"
            "*Số lượng*`;` *Giá nhập*`;` *Ghi chú \\(tùy chọn\\)*",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return STATE_ASK_DETAILS

    if query.data == "imp_save":
        payload = context.user_data.get('imp', {})
        await query.edit_message_text(text="⏳ Đang lưu phiếu nhập, vui lòng chờ...")
        try:
            sheet = connect_to_sheet().worksheet(SHEETS["IMPORT"])
            row_data = [""] * len(IMPORT_COLUMNS)
            row_data[IMPORT_COLUMNS["THOI_GIAN"]]    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            row_data[IMPORT_COLUMNS["MA_PHIEU"]]     = payload.get("voucher", "")
            row_data[IMPORT_COLUMNS["TEN_SAN_PHAM"]] = payload.get("name", "")
            row_data[IMPORT_COLUMNS["MA_SAN_PHAM"]]  = payload.get("code", "")
            row_data[IMPORT_COLUMNS["NGUON"]]        = payload.get("source", "")
            row_data[IMPORT_COLUMNS["SO_LUONG"]]     = payload.get("qty", "")
            row_data[IMPORT_COLUMNS["GIA_NHAP"]]     = payload.get("cost", "")
            row_data[IMPORT_COLUMNS["GHI_CHU"]]      = payload.get("note", "")
            
            sheet.append_row(row_data, value_input_option='USER_ENTERED')
            
            await query.edit_message_text("✅ Đã lưu phiếu nhập hàng thành công\\.", parse_mode="MarkdownV2")
            await show_main_selector(update, context, edit=False)
            
        except Exception as e:
            logger.exception("Lưu phiếu nhập thất bại: %s", e)
            await query.edit_text(f"❌ Lỗi khi lưu vào Google Sheet: {escape_mdv2(str(e))}", parse_mode="MarkdownV2")
            
        context.user_data.clear()
        return ConversationHandler.END

    # Trường hợp còn lại là imp_cancel
    return await on_cancel(update, context)

async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hủy bỏ thao tác nhập hàng và quay về menu chính."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Đã hủy thao tác nhập hàng.")
    
    context.user_data.clear()
    await show_main_selector(update, context, edit=False)
    return ConversationHandler.END


# ====== KHỞI TẠO CONVERSATION HANDLER ======
def get_import_order_conversation_handler() -> ConversationHandler:
    """Tạo và trả về ConversationHandler cho luồng nhập hàng."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_import, pattern=r'^nhap_hang$')],
        states={
            STATE_ASK_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            STATE_PICK_CODE:   [CallbackQueryHandler(on_pick_code, pattern=r'^(imp_code::.+|imp_new_code)$')],
            STATE_NEW_CODE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_code)],
            STATE_PICK_SOURCE: [CallbackQueryHandler(on_pick_source, pattern=r'^(imp_src::.+|imp_new_src)$')],
            STATE_NEW_SOURCE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_source)],
            STATE_ASK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_details)],
            STATE_CONFIRM:     [CallbackQueryHandler(on_confirm, pattern=r'^(imp_save|imp_edit|imp_cancel)$')],
        },
        fallbacks=[CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
        name="import_order_conversation",
        persistent=False,
        allow_reentry=True,
    )