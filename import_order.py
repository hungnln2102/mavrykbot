# import_order.py  — Flow "Nhập Hàng" clone rule từ Thêm Đơn
from __future__ import annotations
from typing import List, Dict, Any, Optional
import re
import logging
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, filters
)

logger = logging.getLogger(__name__)

# ====== STATES ======
ASK_NAME, PICK_CODE, NEW_CODE, PICK_SOURCE, NEW_SOURCE, ASK_DETAILS, CONFIRM = range(7)

# ====== TEXT HELPERS ======
def mdv2_escape(s: str) -> str:
    # dùng chung format giống add_order (MarkdownV2)
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', s or "")

def fmt_summary(d: Dict[str, Any]) -> str:
    return (
        "*Xác nhận Nhập Hàng*\n"
        f"• Mã phiếu: `{mdv2_escape(d.get('voucher',''))}`\n"
        f"• Tên SP: *{mdv2_escape(d.get('name',''))}*\n"
        f"• Mã SP: `{mdv2_escape(d.get('code',''))}`\n"
        f"• Nguồn: *{mdv2_escape(d.get('source',''))}*\n"
        f"• SL: *{mdv2_escape(str(d.get('qty','')))}*\n"
        f"• Giá nhập: *{mdv2_escape(str(d.get('cost','')))}*\n"
        f"• Ghi chú: {mdv2_escape(d.get('note',''))}"
    )

# ====== DATA HELPERS (KẾT NỐI VỚI CODE CŨ) ======
def gen_voucher_no(context: ContextTypes.DEFAULT_TYPE) -> str:
    # Nếu bạn đã có generator bên add_order thì gọi lại ở đây.
    # Tạm thời tạo chuỗi dạng MAVN00001 theo counter trong bot_data.
    n = context.application.bot_data.get("imp_counter", 0) + 1
    context.application.bot_data["imp_counter"] = n
    return f"MAVN{n:05d}"

def search_products_by_name(keyword: str) -> List[Dict[str, str]]:
    """
    TODO: THAY = HÀM GỢI Ý SẢN PHẨM BÊN add_order/utils CỦA BẠN
    Trả về list dict: {'code': 'Adobe_80Gb_4PC_PR2-12m', 'name': 'Adobe 80Gb 4PC PR2 12m'}
    """
    # Ví dụ tạm (để bạn test flow UI):
    demo = [
        {"code": "Adobe_80Gb_4PC_PR2-12m", "name": "Adobe 80Gb 4PC PR2 12m"},
        {"code": "Adobe_CreativeCloud-3m", "name": "Adobe Creative Cloud 3 tháng"},
        {"code": "Canva_Pro-1y", "name": "Canva Pro 1 năm"},
    ]
    kw = keyword.lower()
    return [x for x in demo if kw in x["name"].lower() or kw in x["code"].lower()][:8]

def get_known_sources() -> List[str]:
    """
    TODO: LẤY DANH SÁCH NGUỒN NHẬP từ sheet/config của bạn (giống rule add_order).
    """
    return ["Ades", "Bongmin", "Kho_Phu", "Đại_Lý_A"]

def write_import_row(payload: Dict[str, Any]) -> None:
    """
    TODO: GHI DỮ LIỆU VÀO SHEET "Bảng Nhập Hàng" của bạn.
    Map cột theo thực tế: ví dụ
    [Timestamp, Voucher, ProductName, ProductCode, Source, Qty, UnitCost, Note]
    """
    # Ví dụ chỉ log để bạn thấy payload; thay bằng code ghi Google Sheets của bạn.
    logger.info("[IMPORT_WRITE] %s", payload)

# ====== KEYBOARDS ======
def kbd_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="imp_cancel")]])

def kbd_codes(cands: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{c['name']} · {c['code']}", callback_data=f"imp_code::{c['code']}")] for c in cands]
    rows.append([InlineKeyboardButton("➕ Mã sản phẩm MỚI", callback_data="imp_new_code")])
    rows.append([InlineKeyboardButton("⬅️ Về menu chính", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

def kbd_sources(srcs: List[str]) -> InlineKeyboardMarkup:
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
    """Entry khi bấm 📥 Nhập Hàng"""
    q = update.callback_query
    if q: await q.answer()
    context.user_data['imp'] = {
        "voucher": gen_voucher_no(context),
        "name": "", "code": "",
        "source": "", "qty": "", "cost": "", "note": ""
    }
    text = (
        "*📦 Nhập Hàng*\n"
        f"Mã phiếu: `{mdv2_escape(context.user_data['imp']['voucher'])}`\n\n"
        "👉 Nhập *tên/mã sản phẩm* (vd: `Adobe_80Gb_4PC_PR2-12m`)."
    )
    msg = q.message if q else update.effective_message
    await msg.edit_text(text, parse_mode="MarkdownV2", reply_markup=kbd_cancel())
    return ASK_NAME

async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message and update.message.text or "").strip()
    context.user_data['imp']['name'] = name
    cands = search_products_by_name(name)
    if not cands:
        await update.message.reply_text("❗Không tìm thấy sản phẩm phù hợp. Nhập lại tên khác:", reply_markup=kbd_cancel())
        return ASK_NAME
    await update.message.reply_text("🔎 Chọn *mã sản phẩm* đúng:", parse_mode="MarkdownV2", reply_markup=kbd_codes(cands))
    return PICK_CODE

async def on_pick_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    data = q.data
    if data == "imp_new_code":
        await q.message.edit_text("✳️ Nhập *mã sản phẩm mới* (không dấu cách):", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return NEW_CODE
    if data.startswith("imp_code::"):
        code = data.split("::",1)[1]
        context.user_data['imp']['code'] = code
        # sang bước chọn nguồn
        srcs = get_known_sources()
        await q.message.edit_text("🧭 *Nguồn nhập* là ai? (vd: Ades, Bongmin...)", parse_mode="MarkdownV2", reply_markup=kbd_sources(srcs))
        return PICK_SOURCE
    # fallback
    return PICK_CODE

async def on_new_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = (update.message and update.message.text or "").strip()
    context.user_data['imp']['code'] = code
    srcs = get_known_sources()
    await update.message.reply_text("🧭 *Nguồn nhập* là ai? (vd: Ades, Bongmin...)", parse_mode="MarkdownV2", reply_markup=kbd_sources(srcs))
    return PICK_SOURCE

async def on_pick_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    if q.data == "imp_new_src":
        await q.message.edit_text("✳️ Nhập *tên nguồn mới*:", parse_mode="MarkdownV2", reply_markup=kbd_cancel())
        return NEW_SOURCE
    if q.data.startswith("imp_src::"):
        src = q.data.split("::",1)[1]
        context.user_data['imp']['source'] = src
        # hỏi chi tiết
        await q.message.edit_text(
            "🧾 Nhập chi tiết theo định dạng:\n"
            "*SL*; *Giá nhập*; *Ghi chú (tuỳ chọn)*\n"
            "_Ví dụ_: `5; 120000; hàng đẹp`",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return ASK_DETAILS
    return PICK_SOURCE

async def on_new_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    src = (update.message and update.message.text or "").strip()
    context.user_data['imp']['source'] = src
    await update.message.reply_text(
        "🧾 Nhập chi tiết theo định dạng:\n"
        "*SL*; *Giá nhập*; *Ghi chú (tuỳ chọn)*\n"
        "_Ví dụ_: `5; 120000; hàng đẹp`",
        parse_mode="MarkdownV2", reply_markup=kbd_cancel()
    )
    return ASK_DETAILS

async def on_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message and update.message.text or "").strip()
    # parse "qty; cost; note?"
    parts = [p.strip() for p in text.split(";")]
    qty = parts[0] if parts else ""
    cost = parts[1] if len(parts) > 1 else ""
    note = parts[2] if len(parts) > 2 else ""
    context.user_data['imp']['qty'] = qty
    context.user_data['imp']['cost'] = cost
    context.user_data['imp']['note'] = note

    summary = fmt_summary(context.user_data['imp'])
    await update.message.reply_text(summary, parse_mode="MarkdownV2", reply_markup=kbd_confirm())
    return CONFIRM

async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    data = q.data
    if data == "imp_save":
        payload = context.user_data.get('imp', {})
        try:
            write_import_row(payload)  # <<== GHI SHEET
            await q.message.edit_text("✅ Đã lưu phiếu nhập.", parse_mode="MarkdownV2")
        except Exception as e:
            logger.exception("Save import failed: %s", e)
            await q.message.edit_text(f"❌ Lỗi khi lưu: {mdv2_escape(str(e))}", parse_mode="MarkdownV2")
        return ConversationHandler.END

    if data == "imp_edit":
        # quay lại bước nhập chi tiết
        await q.message.edit_text(
            "🧾 Nhập lại chi tiết theo định dạng:\n"
            "*SL*; *Giá nhập*; *Ghi chú (tuỳ chọn)*",
            parse_mode="MarkdownV2", reply_markup=kbd_cancel()
        )
        return ASK_DETAILS

    # cancel
    await q.message.edit_text("❌ Đã huỷ nhập hàng.")
    return ConversationHandler.END

async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.message.edit_text("❌ Đã huỷ nhập hàng.")
    else:
        await update.message.reply_text("❌ Đã huỷ nhập hàng.")
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
