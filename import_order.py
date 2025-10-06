from __future__ import annotations
import re
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from collections import defaultdict

# Import các hàm và biến dùng chung từ project của bạn
from utils import connect_to_sheet, escape_mdv2
from column import SHEETS, PRICE_COLUMNS, IMPORT_COLUMNS # <-- Import thêm IMPORT_COLUMNS
from menu import show_main_selector

logger = logging.getLogger(__name__)

# ====== STATES ======
(ASK_NAME, PICK_CODE, NEW_CODE, PICK_SOURCE, NEW_SOURCE, ASK_DETAILS, CONFIRM) = range(7)

# ====== TEXT HELPERS ======
def fmt_summary(d: dict) -> str:
    # Helper để format bản tóm tắt, không đổi
    gia_nhap_str = f"{int(d.get('cost', 0)):,} đ" if str(d.get('cost', '')).isdigit() else d.get('cost', '')
    return (
        "*Xác nhận Nhập Hàng*\n"
        f"• Mã phiếu: `{escape_mdv2(d.get('voucher',''))}`\n"
        f"• Tên SP gợi ý: *{escape_mdv2(d.get('name',''))}*\n"
        f"• Mã SP đã chọn: `{escape_mdv2(d.get('code',''))}`\n"
        f"• Nguồn: *{escape_mdv2(d.get('source',''))}*\n"
        f"• Số lượng: *{escape_mdv2(str(d.get('qty','')))}*\n"
        f"• Giá nhập / đơn vị: *{escape_mdv2(gia_nhap_str)}*\n"
        f"• Ghi chú: {escape_mdv2(d.get('note',''))}"
    )

# ====== DATA HELPERS (KẾT NỐI VỚI CODE CŨ) ======
def gen_voucher_no(context: ContextTypes.DEFAULT_TYPE) -> str:
    # Tái sử dụng logic counter
    n = context.application.bot_data.get("imp_counter", 0) + 1
    context.application.bot_data["imp_counter"] = n
    return f"NH{datetime.now().strftime('%y%m%d')}{n:04d}"

def get_price_data() -> list:
    # Hàm tiện ích để lấy dữ liệu từ Bảng Giá
    try:
        sheet_gia = connect_to_sheet().worksheet(SHEETS["PRICE"])
        return sheet_gia.get_all_values()[1:]
    except Exception as e:
        logger.error(f"Lỗi khi tải bảng giá: {e}")
        return []

# ====== KEYBOARDS ======
# Giữ nguyên các hàm tạo keyboard: kbd_cancel, kbd_codes, kbd_sources, kbd_confirm

# ... (Copy y hệt các hàm kbd_* từ file gốc của bạn) ...
def kbd_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]])

def kbd_codes(cands: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{c['name']}", callback_data=f"imp_code::{c['name']}")] for c in cands]
    rows.append([InlineKeyboardButton("➕ Mã sản phẩm MỚI", callback_data="imp_new_code")])
    rows.append([InlineKeyboardButton("⬅️ Về menu chính", callback_data="back_to_menu")]) # Giả sử bạn có handler này
    return InlineKeyboardMarkup(rows)

def kbd_sources(srcs: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(s, callback_data=f"imp_src::{s}")] for s in srcs]
    rows.append([InlineKeyboardButton("➕ Thêm NGUỒN mới", callback_data="imp_new_src")])
    rows.append([InlineKeyboardButton("⬅️ Về menu chính", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

def kbd_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Lưu", callback_data="imp_save")],
        [InlineKeyboardButton("⬅️ Sửa lại", callback_data="imp_edit")],
        [InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")],
    ])

# ====== FLOW ======
async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q: await q.answer()
    
    context.user_data['imp'] = {"voucher": gen_voucher_no(context)}
    
    # === FIX LỖI GỐC ===
    text = (
        "*📦 Nhập Hàng*\n"
        f"Mã phiếu: `{escape_mdv2(context.user_data['imp']['voucher'])}`\n\n"
        "👉 Nhập *tên hoặc mã sản phẩm* \\(vd: `Netflix`\\)\\."
    )
    
    msg_to_edit = q.message if q else update.effective_message
    await msg_to_edit.edit_text(text, parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name_query = update.message.text.strip()
    await update.message.delete()
    context.user_data['imp']['name'] = name_query
    
    price_data = get_price_data()
    if not price_data:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['main_message_id'], text=escape_mdv2("❌ Lỗi kết nối Google Sheet."), parse_mode="MarkdownV2")
        return await on_cancel(update, context)

    # Logic tìm kiếm sản phẩm giống hệt add_order.py
    grouped = defaultdict(list)
    for row in price_data:
        if len(row) > PRICE_COLUMNS["TEN_SAN_PHAM"] and name_query.lower() in row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip().lower():
            grouped[row[PRICE_COLUMNS["TEN_SAN_PHAM"]].strip()].append(row)
    
    context.user_data['price_data_cache'] = price_data # Lưu cache
    context.user_data['grouped_products'] = grouped

    if not grouped:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=update.effective_message.message_id, # Cần ID tin nhắn bot
            text=f"❗Không tìm thấy sản phẩm chứa *{escape_mdv2(name_query)}*\\. Nhập *mã sản phẩm mới*:",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return NEW_CODE

    # Chuyển đổi keys của grouped thành format cho kbd_codes
    candidates = [{'name': name, 'code': ''} for name in grouped.keys()]
    
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=update.effective_message.message_id, # Cần ID tin nhắn bot
        text="🔎 Chọn *sản phẩm* đúng:",
        parse_mode="MarkdownV2",
        reply_markup=kbd_codes(candidates)
    )
    return PICK_CODE

# ... (Các hàm còn lại cần được điều chỉnh tương tự)
# Ví dụ hàm on_pick_code:
async def on_pick_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    data = q.data
    if data == "imp_new_code":
        await q.message.edit_text("✳️ Nhập *mã sản phẩm mới* \\(không dấu cách\\):", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return NEW_CODE
    
    # Mã sản phẩm ở đây là Tên sản phẩm trong bảng giá
    ma_chon = data.split("::", 1)[1]
    context.user_data['imp']['code'] = ma_chon

    # Lấy danh sách nguồn từ sản phẩm đã chọn
    ds_sp = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    sources = sorted(list(set(r[PRICE_COLUMNS["NGUON"]].strip() for r in ds_sp if len(r) > PRICE_COLUMNS["NGUON"] and r[PRICE_COLUMNS["NGUON"]].strip())))

    await q.message.edit_text("🧭 *Nguồn nhập* là ai?", parse_mode="MarkdownV2", reply_markup=kbd_sources(sources))
    return PICK_SOURCE

# ... các hàm on_new_code, on_pick_source, on_new_source, on_details...
# Cần logic tương tự

async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    data = q.data
    if data == "imp_save":
        payload = context.user_data.get('imp', {})
        try:
            # === GHI VÀO SHEET ===
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
            
            await q.message.edit_text("✅ Đã lưu phiếu nhập hàng thành công\\.", parse_mode="MarkdownV2")
            await show_main_selector(update, context, edit=False) # Quay về menu chính
            
        except Exception as e:
            logger.exception("Save import failed: %s", e)
            await q.message.edit_text(f"❌ Lỗi khi lưu: {escape_mdv2(str(e))}", parse_mode="MarkdownV2")
            
        context.user_data.clear()
        return ConversationHandler.END

    # ... (Các logic khác của on_confirm)
    return ConversationHandler.END

async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.message.edit_text("❌ Đã huỷ thao tác nhập hàng\\.")
    else:
        # Trường hợp người dùng gửi tin nhắn thay vì bấm nút
        await update.message.reply_text("❌ Đã huỷ thao tác nhập hàng\\.")
    
    context.user_data.clear()
    await show_main_selector(update, context, edit=True if q else False)
    return ConversationHandler.END

# ====== PUBLIC: expose ConversationHandler ======
def get_import_order_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_import, pattern=r'^nhap_hang$')],
        states={
            ASK_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            PICK_CODE:   [CallbackQueryHandler(on_pick_code, pattern=r'^(imp_code::.+|imp_new_code)$'),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            NEW_CODE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_code),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            PICK_SOURCE: [CallbackQueryHandler(on_pick_source, pattern=r'^(imp_src::.+|imp_new_src)$'),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            NEW_SOURCE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_source),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            ASK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_details),
                          CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
            CONFIRM:     [CallbackQueryHandler(on_confirm, pattern=r'^(imp_save|imp_edit|imp_cancel)$')],
        },
        fallbacks=[CallbackQueryHandler(on_cancel, pattern=r'^imp_cancel$')],
        name="import_order",
        persistent=False,
    )
