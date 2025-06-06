from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, filters
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from utils import connect_to_sheet, generate_unique_id
from menu import show_outer_menu
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

CHON_LOAI_KHACH, TEN_SAN_PHAM, CHON_NGUON_MOI, CHON_GIA_NHAP, CHON_KHACH_HANG, CHON_THONG_TIN_DON, CHON_LINK_KHACH, CHON_MA_SAN_PHAM_MOI, CHON_SLOT, CHON_SO_NGAY, CHON_GIA_BAN, CHON_NOTE = range(12)

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
    sheet = connect_to_sheet().worksheet("Test")
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
    ket_qua = []
    for row in data:
        san_pham = row[0].strip().lower()
        if san_pham.startswith(ten_sp):
            ket_qua.append((row[0], row))
    # ✨ Chỉnh sửa lại tin nhắn trước đó để phản hồi nhập tên sản phẩm
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận tên sản phẩm: *{ten_sp}*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    if not ket_qua:
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
    context.user_data['ds_san_pham'] = ket_qua
    # Tạo danh sách nút chọn mã sản phẩm
    keyboard, row = [], []
    for index, (ma, _) in enumerate(ket_qua):
        row.append(InlineKeyboardButton(text=ma, callback_data=f"chon_ma|{ma}"))
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
    # Tìm dòng tương ứng
    for ma, row in context.user_data.get('ds_san_pham', []):
        if ma == ma_chon:
            context.user_data['dong_san_pham'] = row
            break
    nguon = row[2] if len(row) > 2 else "Không rõ"
    nguon_list = [nguon]
    keyboard, row = [], []
    for index, n in enumerate(nguon_list):
        row.append(InlineKeyboardButton(n, callback_data=f"chon_nguon|{n}"))
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
    # ✨ Sửa lại tin nhắn để hiển thị bước chọn nguồn
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
    nguon = query.data.split("|", 1)[1]
    context.user_data["nguon"] = nguon
    dong_san_pham = context.user_data.get("dong_san_pham", [])
    gia_nhap = dong_san_pham[3] if len(dong_san_pham) > 3 else ""
    context.user_data["gia_nhap"] = gia_nhap
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ])
    # ❗ Phải dùng context.bot để lấy lại Message object
    msg = await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text=f"✅ Đã chọn nguồn: `{nguon}`\n📥 Vui lòng nhập *Thông tin đơn hàng*:",
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
    # Gửi bước tiếp theo
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
    ma_moi = update.message.text.strip()
    context.user_data['ma_chon'] = ma_moi
    # ✨ Edit lại tin nhắn trước để xác nhận mã mới
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã tạo Mã Sản Phẩm: `{ma_moi}` thành công",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi bước tiếp theo: nhập nguồn nhập hàng
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
    # ✅ Xác nhận lại slot (sửa tin nhắn cũ)
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Slot*: `{slot}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # ❗ Sau khi sửa rồi, bây giờ mới gửi bước tiếp theo
    keyboard = [
        [InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "📆 Vui lòng nhập *Số Ngày Đăng Ký*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    # ✅ Lưu đúng message_id của dòng mới nhất
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_SO_NGAY

async def nhap_so_ngay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await remove_previous_buttons(update, context)
    so_ngay = update.message.text.strip()
    if not so_ngay.isdigit():
        msg = await update.message.reply_text("⚠️ Vui lòng chỉ nhập dữ liệu dạng số", parse_mode="Markdown")
        context.user_data["last_keyboard_msg_id"] = msg.message_id
        return CHON_SO_NGAY
    context.user_data["so_ngay"] = so_ngay
    # ✨ Edit lại tin cũ xác nhận số ngày
    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text=f"✅ Đã nhận *Số ngày đăng ký*: `{so_ngay}` ngày",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi bước tiếp theo: nhập giá bán
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(
        "💰 Vui lòng nhập *Giá bán*:",
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

    qr_url = f"https://img.vietqr.io/image/VPB-mavrykstore-compact2.png?amount={gia_value}&addInfo={ma_don}"
    msg = (
        f"✅ *Đơn hàng `{ma_don}` đã được tạo thành công!*\n\n"

        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"🔹 *Tên:* {info.get('ten_san_pham', '')}\n"
        f"📝 *Mô tả:* {info.get('thong_tin_don', '')}\n"
        + (f"🧩 *Slot:* {info['slot']}\n" if info.get("slot") else "")
        + f"📆 *Bắt đầu:* {info.get('ngay_bat_dau', '')}\n"
        + f"⏳ *Thời hạn:* {info.get('so_ngay', '')} ngày\n"
        + f"📅 *Hết hạn:* {ngay_het_han}\n"
        + f"💵 *Giá bán:* {info.get('gia_ban', '')} VNĐ\n"

        f"\n━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"

        f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        f"🔸 *Tên:* {info.get('khach_hang', '')}\n"
        + (f"🔗 *Liên hệ:* {info['link_khach']}\n" if info.get("link_khach") else "") + ""

        f"\n━━━━━━━━━━ 💳 ━━━━━━━━━━\n\n"

        f"📢 *HƯỚNG DẪN THANH TOÁN*\n"
        f"✅ Vui lòng chuyển khoản đúng nội dung và số tiền.\n"
        f"📞 Mọi thắc mắc xin liên hệ lại Shop để được hỗ trợ.\n\n"
        f"🙏 *Cảm ơn quý khách đã tin tưởng và ủng hộ Mavryk Store!* ✨"
    )

    sheet = connect_to_sheet().worksheet("Test")

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
                info["so_ngay"],
                ngay_het_han,
                f"=I{idx}-TODAY()",  # ✅ Công thức tính số ngày còn lại
                info.get("nguon", ""),
                info.get("gia_nhap", ""),
                info.get("gia_ban", ""),
                "",
                info.get("note", ""),
                "Chưa Thanh Toán"
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
    # ✅ Edit lại dòng "Vui lòng nhập Slot..." thành "Đã bỏ qua..."
    try:
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=context.user_data.get("last_keyboard_msg_id"),
            text="✅ Đã bỏ qua mục *Slot*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[⚠️ Không thể chỉnh sửa tin nhắn cũ]: {e}")
    # Gửi bước tiếp theo
    keyboard = [[InlineKeyboardButton("❌ Hủy Đơn", callback_data="cancel_add")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.message.reply_text(
        "📆 Vui lòng nhập *Số Ngày Đăng Ký*:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["last_keyboard_msg_id"] = msg.message_id
    return CHON_SO_NGAY

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
        CHON_SO_NGAY: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_so_ngay)
        ],
        CHON_GIA_BAN: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_gia_ban)
        ],
        CHON_NOTE: [
            CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            CallbackQueryHandler(skip_note, pattern="^skip_note$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_note)
        ]  # Sẽ bổ sung xử lý sau
    },
    fallbacks=[CallbackQueryHandler(cancel_add, pattern="^cancel_add$")],
)
