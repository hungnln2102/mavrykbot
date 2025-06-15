from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, filters
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
import re
from utils import connect_to_sheet, generate_unique_id
from menu import show_outer_menu
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from telegram.helpers import escape_markdown
from collections import defaultdict

CHON_LOAI_KHACH, TEN_SAN_PHAM, CHON_NGUON_MOI, CHON_GIA_NHAP,CHON_KHACH_HANG, CHON_THONG_TIN_DON, CHON_LINK_KHACH, CHON_MA_SAN_PHAM_MOI, CHON_SLOT, CHON_GIA_BAN, CHON_NOTE = range(11)

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Khách Lẻ", callback_data="loai_khach_le"),
            InlineKeyboardButton("CTV", callback_data="loai_khach_ctv")
        ],
        [
            InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "📦 Khởi Tạo Đơn Hàng Mới\n\nVui lòng lựa chọn phân loại khách hàng để tiếp tục:"
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        sent = await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = sent.message_id
    return CHON_LOAI_KHACH

async def chon_loai_khach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    loai_khach = query.data.replace("loai_khach_", "")
    context.user_data["loai_khach"] = loai_khach
    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")
    ma_don = generate_unique_id(sheet, loai_khach)
    context.user_data["ma_don"] = ma_don
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # 🧾 Chỉnh sửa lại tin nhắn cũ thành thông báo mã đơn hàng mới
    msg = await query.message.edit_text(
        f"🧾 Mã đơn hàng: `{ma_don}` đã được khởi tạo thành công.\n\nVui lòng nhập *Tên Sản Phẩm*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return TEN_SAN_PHAM

async def nhap_ten_san_pham(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    ten_sp = update.message.text.strip().lower()
    context.user_data['ten_san_pham'] = ten_sp
    sheet = connect_to_sheet().worksheet("Bảng Giá")
    data = sheet.get_all_values()[1:]

    # Gom nhóm các mã giống nhau
    grouped = defaultdict(list)
    for row in data:
        san_pham = row[0].strip()
        if ten_sp in san_pham.lower():
            grouped[san_pham].append(row)

    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận tên sản phẩm: *{ten_sp}*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    if not grouped:
        keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            f"❌ Không tìm thấy các mã sản phẩm của *{ten_sp}* trong *Dữ Liệu*.\n\n"
            "✏️ Vui lòng nhập *Mã sản phẩm Mới* để tiếp tục:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_MA_SAN_PHAM_MOI

    context.user_data['grouped_products'] = grouped
    keyboard, row = [], []
    for index, ma_sp in enumerate(grouped.keys()):
        row.append(InlineKeyboardButton(text=ma_sp, callback_data=f"chon_ma|{ma_sp}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("✏️ Nhập Mã Sản Phẩm Mới", callback_data="nhap_ma_moi"),
        InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        f"📦 Vui lòng chọn *Mã sản phẩm* phù hợp với: *{ten_sp}*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return TEN_SAN_PHAM

async def chon_ma_san_pham(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ma_chon = query.data.split("|", 1)[1]
    context.user_data['ma_chon'] = ma_chon
    so_ngay = extract_days_from_ma_sp(ma_chon)
    if so_ngay > 0:
        context.user_data['so_ngay'] = str(so_ngay)
        context.user_data['skip_so_ngay'] = True  # Gắn cờ để bỏ qua bước hỏi
    else:
        context.user_data['skip_so_ngay'] = False

    ds = context.user_data.get("grouped_products", {}).get(ma_chon, [])
    if not ds:
        await query.message.reply_text("⚠️ Không tìm thấy nguồn cho mã sản phẩm đã chọn.")
        return TEN_SAN_PHAM

    context.user_data['ds_san_pham'] = ds  # Lưu lại danh sách nguồn cho mã này

    keyboard, row = [], []
    for r in ds:
        nguon = r[2] if len(r) > 2 else "Không rõ"
        gia = r[3] if len(r) > 3 else "--"
        label = f"{nguon} - {gia}"
        callback = f"chon_nguon|{nguon}|{gia}"
        row.append(InlineKeyboardButton(label, callback_data=callback))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("➕ Nguồn Mới", callback_data="nguon_moi"),
        InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.message.edit_text(
        f"📦 Mã sản phẩm: `{ma_chon}`\nVui lòng chọn *Nguồn hàng*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return TEN_SAN_PHAM

async def chon_nguon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) < 3:
        await query.message.reply_text("⚠️ Dữ liệu nguồn không hợp lệ.")
        return ConversationHandler.END

    nguon = parts[1].strip()
    gia_raw = parts[2].strip().replace(",", "").replace(" đ", "").replace(".", "")
    try:
        gia_value = int(gia_raw)
    except:
        gia_value = 0

    gia_format = "{:,} đ".format(gia_value)

    # ✅ Lưu giá nhập
    context.user_data["nguon"] = nguon
    context.user_data["gia_nhap"] = gia_format
    context.user_data["gia_nhap_value"] = gia_value

    # ✅ Tự động lấy giá bán từ bảng giá theo MAVC / MAVL
    ma_don = context.user_data.get("ma_don", "")
    ds = context.user_data.get("ds_san_pham", [])

    gia_ban = 0
    for row in ds:
        if row[2].strip() == nguon:  # So sánh nguồn hàng khớp
            try:
                if ma_don.startswith("MAVC") and len(row) > 4:
                    gia_ban = int(row[4].strip().replace(",", "").replace(" đ", "").replace(".", ""))
                elif ma_don.startswith("MAVL") and len(row) > 5:
                    gia_ban = int(row[5].strip().replace(",", "").replace(" đ", "").replace(".", ""))
            except:
                gia_ban = 0
            break

    context.user_data["gia_ban_value"] = gia_ban
    context.user_data["gia_ban"] = f"{gia_ban:,} đ" if gia_ban else "--"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ])
    msg = await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text=f"✅ Đã chọn nguồn: `{nguon}` với giá nhập: `{gia_format}`\n💵 Giá bán tự động: `{context.user_data['gia_ban']}`\n\n📥 Vui lòng nhập *Thông tin đơn hàng*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_THONG_TIN_DON


async def chon_nguon_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text="📥 Vui lòng nhập *Nguồn hàng mới*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_NGUON_MOI

async def nhap_nguon_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    nguon = update.message.text.strip()
    context.user_data["nguon"] = nguon
    # ✨ Cập nhật lại tin nhắn cũ để báo đã nhập xong nguồn
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận nguồn: `{nguon}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi prompt kế tiếp
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent = await update.message.reply_text(
        "💰 Vui lòng nhập *Giá nhập* cho sản phẩm:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = sent.message_id
    return CHON_GIA_NHAP

async def nhap_gia_nhap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    gia_nhap_raw = update.message.text.strip().replace(",", ".")
    try:
        gia_value = int(float(gia_nhap_raw) * 1000)
    except:
        keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            "⚠️ *Giá nhập không hợp lệ*. Vui lòng chỉ nhập số (vd: `100`, `100.2`, `100,2`):",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_GIA_NHAP
    # ✅ Nếu hợp lệ, lưu giá trị
    context.user_data["gia_nhap"] = "{:,} đ".format(gia_value)
    context.user_data["gia_nhap_value"] = gia_value
    # ✨ Cập nhật lại tin nhắn trước đó để xác nhận đã nhập
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Giá nhập*: `{context.user_data['gia_nhap']}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi prompt kế tiếp
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "📥 Vui lòng nhập *Thông tin đơn hàng*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_THONG_TIN_DON

async def nhap_thong_tin_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    thong_tin = update.message.text.strip()
    context.user_data["thong_tin_don"] = thong_tin
    # ✨ Edit lại tin nhắn cũ để xác nhận
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Thông tin đơn hàng*: `{thong_tin}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi prompt kế tiếp: Nhập tên khách hàng
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "👤 Vui lòng nhập *tên khách hàng*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_KHACH_HANG

async def nhap_khach_hang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    khach = update.message.text.strip()
    context.user_data["khach_hang"] = khach

    # ✨ Xác nhận lại bước vừa nhập bằng cách sửa tin nhắn cũ
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Tên khách hàng*: `{khach}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    # ⚙️ Nếu đã có số ngày từ mã sản phẩm → bỏ qua luôn bước nhập số ngày
    if context.user_data.get("skip_so_ngay"):
        context.user_data["slot"] = ""  # Nếu chưa nhập thì bỏ qua slot luôn
        keyboard = [
            [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_link")],
            [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            "🔗 Vui lòng nhập *thông tin liên hệ* hoặc bấm 'Bỏ Qua':",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_LINK_KHACH

    # ⏩ Nếu không có skip, gửi bước tiếp theo như cũ
    keyboard = [
        [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_link")],
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "🔗 Vui lòng nhập *thông tin liên hệ* hoặc bấm 'Bỏ Qua':",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_LINK_KHACH

async def nhap_link_khach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    link = update.message.text.strip()
    context.user_data["link_khach"] = link
    # ✨ Edit lại tin nhắn trước để xác nhận đã nhập
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Thông tin liên hệ*: `{link}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi bước kế tiếp
    keyboard = [
        [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_slot")],
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "📌 Vui lòng nhập *Slot* hoặc bấm 'Bỏ Qua':",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_SLOT

async def nhap_ma_san_pham_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text="✏️ Vui lòng nhập *Mã Sản Phẩm mới* để tạo:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_MA_SAN_PHAM_MOI

async def xu_ly_ma_san_pham_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)

    # ✅ Chuẩn hóa các dấu gạch thành "--" trước khi xử lý
    ma_moi = update.message.text.strip().replace("—", "--").replace("–", "--").replace("－", "--")
    context.user_data['ma_chon'] = ma_moi

    # ✅ Tự động tính số ngày nếu có định dạng --Xm
    so_ngay = extract_days_from_ma_sp(ma_moi)
    if so_ngay > 0:
        context.user_data["so_ngay"] = str(so_ngay)
        context.user_data["skip_so_ngay"] = True
    else:
        context.user_data["skip_so_ngay"] = False

    # ✨ Edit lại tin nhắn trước để xác nhận
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã tạo Mã Sản Phẩm: `{ma_moi}` thành công",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    # 👉 Gửi bước tiếp theo: nhập nguồn nhập hàng
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(
        "📦 Vui lòng nhập *Nguồn Nhập Hàng*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_NGUON_MOI

async def nhap_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    slot = update.message.text.strip()
    context.user_data["slot"] = slot

    # ✅ Xác nhận lại slot vừa nhập
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Slot*: `{slot}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    # ✅ Nếu đã có giá bán từ bảng giá → bỏ qua bước nhập giá bán
    if context.user_data.get("gia_ban_value"):
        keyboard = [
            [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_note")],
            [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(
            "📝 Vui lòng nhập *Ghi chú (nếu có)* hoặc bấm 'Bỏ Qua':",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_NOTE

    # ❗ Nếu chưa có giá bán → yêu cầu nhập thủ công
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "💰 Vui lòng nhập *Giá bán*: ",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_GIA_BAN


async def nhap_gia_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    try:
        gia_value = int(float(update.message.text.strip().replace(",", ".")) * 1000)
    except:
        msg = await update.message.reply_text("⚠️ Vui lòng chỉ nhập dữ liệu dạng số", parse_mode="Markdown")
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_GIA_BAN
    context.user_data.update({
        "gia_ban_value": gia_value,
        "gia_ban": f"{gia_value:,} đ"
    })
    # Cập nhật lại tin nhắn cũ là đã nhập thành công
    try:
        await context.bot.edit_message_text(
        chat_id=update.message.chat_id,
        message_id=context.user_data.get("last_keyboard_msg_id"),
        text=f"✅ Đã nhận *Giá bán*: `{context.user_data['gia_ban']}`",
        parse_mode="Markdown"
    )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi prompt tiếp theo
    keyboard = [
        [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_note")],
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(
        "📝 Vui lòng nhập *Ghi chú (nếu có)* hoặc bấm 'Bỏ Qua':",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_NOTE

async def nhap_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    note = update.message.text.strip()
    context.user_data["note"] = note
    # ✨ Xác nhận ghi chú bằng cách chỉnh sửa tin nhắn cũ
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Ghi chú*: `{note}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    return await hoan_tat_don(update, context)

def tinh_ngay_het_han(ngay_bat_dau_str, so_ngay_dang_ky):
    try:
        ngay_bat_dau = datetime.strptime(ngay_bat_dau_str, "%d/%m/%Y")
        tong_ngay = int(so_ngay_dang_ky)
        so_nam = tong_ngay // 365
        so_ngay_con_lai = tong_ngay % 365
        so_thang = so_ngay_con_lai // 30
        so_ngay_du = so_ngay_con_lai % 30

        # ✅ Gộp cộng cả năm, tháng, ngày dư (trừ 1 để tính cả ngày bắt đầu)
        ngay_het_han = ngay_bat_dau + relativedelta(
            years=so_nam,
            months=so_thang,
            days=so_ngay_du - 1
        )
        return ngay_het_han.strftime("%d/%m/%Y")
    except Exception as e:
        print(f"[LỖI TÍNH NGÀY]: {e}")
        return ""


async def hoan_tat_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = context.user_data
    ma_don = info.get("ma_don", "")
    gia_value = info.get("gia_ban_value", 0)
    ngay_bat_dau_str = datetime.now().strftime("%d/%m/%Y")
    info["ngay_bat_dau"] = ngay_bat_dau_str
    ngay_het_han = tinh_ngay_het_han(ngay_bat_dau_str, info.get("so_ngay", "0"))

    # Escape dữ liệu động để tránh lỗi Markdown
    ma_don_md = escape_markdown(ma_don, version=1)
    ma_san_pham = escape_markdown(info.get("ma_chon", ""), version=1)
    ten_san_pham = escape_markdown(info.get("ten_san_pham", ""), version=1)
    mo_ta = escape_markdown(info.get("thong_tin_don", ""), version=1)
    slot = escape_markdown(info.get("slot", ""), version=1) if info.get("slot") else ""
    ngay_bat_dau = escape_markdown(info.get("ngay_bat_dau", ""), version=1)
    so_ngay = escape_markdown(info.get("so_ngay", ""), version=1)
    ngay_het_han_md = escape_markdown(ngay_het_han, version=1)
    gia_ban = escape_markdown(info.get("gia_ban", ""), version=1)
    khach_hang = escape_markdown(info.get("khach_hang", ""), version=1)
    link_khach = escape_markdown(info.get("link_khach", ""), version=1) if info.get("link_khach") else ""

    qr_url = f"https://img.vietqr.io/image/VPB-mavpre-compact2.png?amount={gia_value}&addInfo={ma_don}"

    msg = (
        f"✅ Đơn hàng `{ma_don_md}` đã được tạo thành công!\n\n"

        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"🔹 *Tên:* {ma_san_pham}\n"
        f"📝 *Thông Tin Đơn Hàng:* {mo_ta}\n"
        + (f"🧩 *Slot:* {slot}\n" if slot else "")
        + f"📆 *Ngày Bắt đầu:* {ngay_bat_dau}\n"
        + f"⏳ *Thời hạn:* {so_ngay} ngày\n"
        + f"📅 *Ngày Hết hạn:* {ngay_het_han_md}\n"
        + f"💵 *Giá bán:* {gia_ban}\n"

        f"\n━━━━━━ 👤 ━━━━━━\n\n"

        f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        f"🔸 *Tên Khách Hàng:* {khach_hang}\n"
        + (f"🔗 *Thông Tin Liên hệ:* {link_khach}\n" if link_khach else "")

        + f"\n━━━━━━ 💳 ━━━━━━\n\n"

        f"📢 *HƯỚNG DẪN THANH TOÁN*\n"
        f"✅ Vui lòng chuyển khoản đúng nội dung và số tiền.\n"
        f"📞 Mọi thắc mắc xin liên hệ lại Shop để được hỗ trợ.\n\n"
        f"🙏 *Cảm ơn quý khách đã tin tưởng và ủng hộ Mavryk Store!* ✨"
    )

    sheet = connect_to_sheet().worksheet("Bảng Đơn Hàng")

    # --- Ghi dữ liệu vào dòng trống đầu tiên ---
    columns_to_check = [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 14]
    all_columns = [sheet.col_values(col) for col in columns_to_check]
    max_row = sheet.row_count

    for idx in range(2, max_row + 1):
        row_has_data = any(
            col[idx - 1].strip() if idx <= len(col) and col[idx - 1] else ""
            for col in all_columns
        )
        if not row_has_data:
            row_data = [
                ma_don,
                info.get("ma_chon", ""),
                info.get("thong_tin_don", ""),
                info.get("khach_hang", ""),
                info.get("link_khach", ""),
                info.get("slot", ""),
                info["ngay_bat_dau"],
                info.get("so_ngay", "0"),
                ngay_het_han,
                f"=I{idx}-TODAY()",  # ✅ Công thức tính số ngày còn lại
                info.get("nguon", ""),
                info.get("gia_nhap_value", ""),
                info.get("gia_ban_value", ""),
                f"=M{idx}*J{idx}/H{idx}",
                info.get("note", ""),
                f"=IF(J{idx}<=0; \"\"; IF(AND(J{idx}>4; Q{idx}=TRUE); \"Đã Thanh Toán\"; \"Chưa Thanh Toán\"))"
            ]
            sheet.update(f"A{idx}:P{idx}", [row_data], value_input_option="USER_ENTERED")
            break
    else:
        print("❌ Không tìm thấy dòng phù hợp để ghi.")

    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="Markdown")
    await show_outer_menu(update, context)
    return ConversationHandler.END

# Các mục Skip và Cancel
async def skip_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["slot"] = ""

    # ✅ Xác nhận bỏ qua slot
    try:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text="✅ Đã bỏ qua mục *Slot*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    # ✅ Nếu đã có giá bán → bỏ qua bước nhập, chuyển sang ghi chú
    if context.user_data.get("gia_ban_value"):
        keyboard = [
            [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_note")],
            [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await query.message.reply_text(
            "📝 Vui lòng nhập *Ghi chú (nếu có)* hoặc bấm 'Bỏ Qua':",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_NOTE

    # ❗ Nếu chưa có giá bán → yêu cầu nhập thủ công
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.message.reply_text(
        "💰 Vui lòng nhập *Giá bán*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_GIA_BAN

async def skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["note"] = ""
    # ✨ Chỉnh sửa lại tin nhắn trước để xác nhận bỏ qua
    try:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text="✅ Đã bỏ qua mục *Ghi chú*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # 👉 Tạo lại update giả để gọi hoan_tat_don
    fake_update = Update(update.update_id, message=query.message)
    return await hoan_tat_don(fake_update, context)

async def skip_link_khach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # ✅ Xóa thông tin liên hệ cũ nếu có
    context.user_data.pop("link_khach", None)

    # ✨ Edit lại tin nhắn cũ để phản hồi đã bỏ qua
    try:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text="✅ Đã bỏ qua mục *Thông Tin Liên Hệ*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")

    # Chuyển sang bước kế tiếp: nhập Slot
    keyboard = [
        [InlineKeyboardButton("⏭ Bỏ Qua", callback_data="skip_slot")],
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.message.reply_text(
        "📌 Vui lòng nhập *Slot* hoặc bấm 'Bỏ Qua':",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_SLOT


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    context.user_data.clear()  # 🔥 Xóa toàn bộ dữ liệu phiên làm việc
    await query.message.reply_text("❌ Đơn hàng đã được hủy.")
    fake_update = Update(update.update_id, message=query.message)
    await show_outer_menu(fake_update, context)
    return ConversationHandler.END

async def remove_previous_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_id = context.user_data.get("last_keyboard_msg_id")
        if update.message:
            chat_id = update.message.chat_id
        elif update.callback_query:
            chat_id = update.callback_query.message.chat_id
        else:
            print("[⚠️ Không thể xác định chat_id]")
            return
        if message_id:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None
            )
    except Exception as e:
        print(f"[⚠️ Không thể xóa nút cũ]: {e}")

def extract_days_from_ma_sp(ma_sp: str) -> int:
    match = re.search(r"--(\d+)m", ma_sp.lower())
    if match:
        thang = int(match.group(1))
        if thang == 12:
            return 365
        elif thang == 24:
            return 730
        else:
            return thang * 30
    return 0

# Khai báo ConversationHandler tạm thời để tránh lỗi import
add_order_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add, pattern="^add$")],
    states={
        CHON_LOAI_KHACH: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(chon_loai_khach)
        ],
        TEN_SAN_PHAM: [
            CallbackQueryHandler(nhap_ma_san_pham_moi, pattern="^nhap_ma_moi$"),
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(chon_ma_san_pham, pattern=r"^chon_ma\|"),
            CallbackQueryHandler(chon_nguon, pattern=r"^chon_nguon\|"),
            CallbackQueryHandler(chon_nguon_moi, pattern="^nguon_moi$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_ten_san_pham)
        ],
        CHON_MA_SAN_PHAM_MOI: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, xu_ly_ma_san_pham_moi)
        ],
        CHON_NGUON_MOI: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_nguon_moi)
        ],
        CHON_GIA_NHAP: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_nhap)
        ],
        CHON_KHACH_HANG: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_khach_hang)
        ],
        CHON_LINK_KHACH: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(skip_link_khach, pattern="^skip_link$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_link_khach)
        ],
        CHON_THONG_TIN_DON: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_thong_tin_don)
        ],
        CHON_SLOT: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(skip_slot, pattern="^skip_slot$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_slot)
        ],
        CHON_GIA_BAN: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_ban)
        ],
        CHON_NOTE: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(skip_note, pattern="^skip_note$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_note)
        ]
    },
    fallbacks=[CallbackQueryHandler(cancel_add, pattern="^cancel_add$")],
)