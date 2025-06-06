async def hoan_tat_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = context.user_data
    ma_don = info.get("ma_don", "")
    gia_value = info.get("gia_ban_value", 0)
    ngay_bat_dau_str = datetime.now().strftime("%d/%m/%Y")
    info["ngay_bat_dau"] = ngay_bat_dau_str
    ngay_het_han = tinh_ngay_het_han(ngay_bat_dau_str, info.get("so_ngay", "0"))

    qr_url = f"https://img.vietqr.io/image/VPB-mavrykstore-compact2.png?amount={gia_value}&addInfo={ma_don}"

    msg = (
        f"✅ *Đơn hàng `{ma_don}` đã được khởi tạo thành công!*\n\n"
        f"✧═════• ༺ 𝐓𝐡𝐨̂𝐧𝐠 𝐓𝐢𝐧 𝐒𝐚̉𝐧 𝐏𝐡𝐚̂̉𝐦 ༻ •═════✧\n"
        f"📌 *Tên sản phẩm:* {info.get('ten_san_pham', '')}\n"
        f"📝 *Chi tiết:* {info.get('thong_tin_don', '')}\n"
        + (f"🧩 *Slot:* {info['slot']}\n" if info.get("slot") else "")
        + f"⏳ *Thời hạn:* {info.get('so_ngay', '')} ngày\n"
        + f"📅 *Hết hạn:* {ngay_het_han}\n"
        + f"💵 *Giá bán:* {info.get('gia_ban', '')} VNĐ\n\n"
        f"✧═════• ༺ 𝐊𝐡𝐚́𝐜𝐡 𝐇𝐚̀𝐧𝐠 ༻ •═════✧\n"
        f"👤 *Tên:* {info.get('khach_hang', '')}\n"
        f"🔗 *Liên hệ:* {info.get('link_khach')}\n\n"
        f"✧═════• ༺ 𝐓𝐡𝐨̂𝐧𝐠 𝐁𝐚́𝐨 ༻ •═════✧\n"
        f"💬 Vui lòng thanh toán để đơn hàng được xử lý sớm nhất.\n"
        f"📞 Mọi thắc mắc xin liên hệ với Shop để được hỗ trợ.\n"
        f"🙏 *Cảm ơn quý khách đã tin tưởng và ủng hộ Mavryk Store!* ✨"
    )

    # ✅ Ghi dữ liệu đơn hàng vào Google Sheet
    sheet = connect_to_sheet().worksheet("Test")
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
        "",  # Cột J (ngày còn lại - sẽ chèn công thức sau)
        info.get("nguon", ""),
        info.get("gia_nhap", ""),
        info.get("gia_ban", ""),
        "",  # Cột N
        info.get("note", ""),
        "Chưa Thanh Toán"
    ]
    sheet.append_row(row_data, value_input_option="USER_ENTERED")

    # ✅ Tìm dòng vừa thêm để ghi công thức vào cột J
    values = sheet.get_all_values()
    for i in range(len(values), 0, -1):
        if any(cell.strip() for cell in values[i - 1]):
            row_index = i
            break

    # ✅ Cập nhật công thức tính ngày còn lại
    sheet.update_acell(f"J{row_index}", f'=IF(I{row_index}="","",I{row_index}-TODAY())')

    # ✅ Gửi QR kèm thông báo
    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="Markdown")

    # ✅ Trở lại menu chính
    await show_outer_menu(update, context)
    return ConversationHandler.END
