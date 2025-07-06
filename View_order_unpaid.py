import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from utils import connect_to_sheet, append_to_sheet # Giả sử có hàm append_to_sheet
from menu import show_outer_menu
from collections import OrderedDict
from column import SHEETS, ORDER_COLUMNS
import logging

logger = logging.getLogger(__name__)

def escape_markdown(text):
    """Hàm escape các ký tự đặc biệt cho chế độ MarkdownV2 của Telegram."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', str(text))

def extract_unpaid_orders():
    """Tải và cache các đơn chưa thanh toán theo logic gốc."""
    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        data = sheet.get_all_values()
        orders_dict = OrderedDict()

        # TỐI ƯU: Thêm enumerate để lấy row_index
        for i, row in enumerate(data[1:], start=2):  # Dữ liệu bắt đầu từ dòng 2
            try:
                ma_don = row[ORDER_COLUMNS["ID_DON_HANG"]].strip()
                check = str(row[ORDER_COLUMNS["CHECK"]]).strip()

                # KHÔI PHỤC: Lấy và xử lý cột "Còn lại"
                days_left_raw = row[ORDER_COLUMNS["CON_LAI"]]
                # Xử lý an toàn nếu ô 'Còn lại' trống hoặc không phải là số
                days_left = float(days_left_raw.strip()) if days_left_raw and days_left_raw.strip().replace(".", "", 1).isdigit() else 0
            
            except (IndexError, ValueError):
                # Bỏ qua dòng nếu thiếu cột hoặc dữ liệu không hợp lệ
                continue
            
            # KHÔI PHỤC: Áp dụng lại logic lọc như file ban đầu của bạn
            if ma_don and check == "" and days_left > 4:
                # TỐI ƯU: Lưu cả dữ liệu và chỉ số dòng vào cache
                orders_dict[ma_don] = {"data": row, "row_index": i}

        return orders_dict
    except Exception as e:
        logger.error(f"Lỗi khi tải đơn chưa thanh toán: {e}")
        return OrderedDict() # Trả về dict rỗng nếu có lỗi

def build_order_text(row_data, index, total):
    """Tạo nội dung tin nhắn chi tiết cho đơn hàng chưa thanh toán."""
    # 1. Lấy dữ liệu thô từ row
    ma_don_raw = row_data[ORDER_COLUMNS["ID_DON_HANG"]].strip()
    product_raw = row_data[ORDER_COLUMNS["SAN_PHAM"]].strip()
    thong_tin_don_raw = row_data[ORDER_COLUMNS["THONG_TIN_DON"]].strip()
    ten_khach_raw = row_data[ORDER_COLUMNS["TEN_KHACH"]].strip()
    link_khach_raw = row_data[ORDER_COLUMNS["LINK_KHACH"]].strip()
    slot_raw = row_data[ORDER_COLUMNS["SLOT"]].strip()
    ngay_dang_ky_raw = row_data[ORDER_COLUMNS["NGAY_DANG_KY"]].strip()
    so_ngay_raw = row_data[ORDER_COLUMNS["SO_NGAY"]].strip()
    ngay_het_han_raw = row_data[ORDER_COLUMNS["HET_HAN"]].strip()
    gia_ban_raw = row_data[ORDER_COLUMNS["GIA_BAN"]].strip()

    # 2. Escape tất cả dữ liệu text để tương thích với MarkdownV2
    product_md = escape_markdown(product_raw)
    ma_don_md = escape_markdown(ma_don_raw)
    info_md = escape_markdown(thong_tin_don_raw)
    ten_khach_md = escape_markdown(ten_khach_raw)
    link_khach_md = escape_markdown(link_khach_raw)
    slot_md = escape_markdown(slot_raw)
    ngay_dang_ky_md = escape_markdown(ngay_dang_ky_raw)
    so_ngay_md = escape_markdown(so_ngay_raw)
    ngay_het_han_md = escape_markdown(ngay_het_han_raw)
    gia_md = escape_markdown("{:,} đ".format(int(gia_ban_raw.replace(",", ""))) if gia_ban_raw.isdigit() else gia_ban_raw)

    # 3. Xây dựng nội dung tin nhắn với định dạng chi tiết
    header = f"📋 *Đơn hàng chưa thanh toán* `({index + 1}/{total})`\n"
    header += f"*{escape_markdown('Mã đơn:')}* `{ma_don_md}`"

    body = (
        f"📦 *THÔNG TIN SẢN PHẨM*\n"
        f"🔸 *Tên:* {product_md}\n"
        f"📝 *Mô tả:* {info_md}\n" +
        (f"🧩 *Slot:* {slot_md}\n" if slot_raw else "") +
        (f"📅 Ngày đăng ký: {ngay_dang_ky_md}\n" if ngay_dang_ky_raw else "") +
        f"⏳ *Thời hạn:* {so_ngay_md} ngày\n" +
        (f"⏳ Ngày hết hạn: {ngay_het_han_md}\n" if ngay_het_han_raw else "") +
        f"💵 *Giá bán:* {gia_md}\n\n"
        f"━━━━━━━━━━ 👤 ━━━━━━━━━━\n\n"
        f"👤 *THÔNG TIN KHÁCH HÀNG*\n"
        f"🔸 *Tên:* {ten_khach_md}\n" +
        (f"🔗 *Liên hệ:* {link_khach_md}\n" if link_khach_raw else "")
    )
    
    return f"{header}\n{escape_markdown('—' * 20)}\n\n{body}"

async def view_unpaid_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu quy trình xem đơn chưa thanh toán."""
    query = update.callback_query
    await query.answer("Đang tải dữ liệu...")
    
    orders = extract_unpaid_orders()

    if not orders:
        # TỐI ƯU: Edit tin nhắn hiện tại thay vì xóa/gửi mới
        await query.edit_message_text("✅ Tuyệt vời! Không có đơn hàng nào chưa thanh toán.")
        return

    context.user_data["unpaid_orders"] = orders
    context.user_data["unpaid_index"] = 0
    await show_unpaid_order(update, context, "stay")

async def show_unpaid_order(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    """Hiển thị một đơn hàng chưa thanh toán và các nút bấm."""
    query = update.callback_query
    await query.answer()

    orders: OrderedDict = context.user_data.get("unpaid_orders", OrderedDict())
    index = context.user_data.get("unpaid_index", 0)
    keys = list(orders.keys())

    if direction == "next":
        index += 1
    elif direction == "prev":
        index -= 1
    context.user_data["unpaid_index"] = index

    # Lấy thông tin đơn hàng hiện tại
    ma_don = keys[index]
    row_data = orders[ma_don]["data"]
    text = build_order_text(row_data, index, len(keys))

    # Xây dựng các nút bấm
    buttons = []
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Back", callback_data="prev_unpaid"))
    if index < len(keys) - 1:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data="next_unpaid"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("✅ Đã Thanh Toán", callback_data=f"paid_unpaid|{ma_don}"),
        InlineKeyboardButton("🗑️ Xóa đơn", callback_data=f"delete_unpaid|{ma_don}"),
        InlineKeyboardButton("🔚 Kết thúc", callback_data="exit_unpaid"),
    ])
    reply_markup = InlineKeyboardMarkup(buttons)

    # TỐI ƯU: Luôn edit tin nhắn để có trải nghiệm liền mạch
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=reply_markup)

async def handle_action_and_update_view(update: Update, context: ContextTypes.DEFAULT_TYPE, ma_don: str, action_type: str):
    """Hàm chung để xử lý hành động (xóa, đánh dấu đã trả) và cập nhật giao diện."""
    query = update.callback_query
    orders: OrderedDict = context.user_data.get("unpaid_orders", OrderedDict())
    
    order_info = orders.get(ma_don)
    if not order_info:
        await query.answer("❗️ Lỗi: Không tìm thấy đơn hàng trong cache.", show_alert=True)
        return

    row_idx_to_action = order_info["row_index"]

    try:
        sheet = connect_to_sheet().worksheet(SHEETS["ORDER"])
        if action_type == "delete":
            # TỐI ƯU: Thao tác trực tiếp trên sheet bằng row_index
            sheet.delete_rows(row_idx_to_action)
            await query.answer("Đã xóa đơn hàng.")
            # SỬA LỖI: Cập nhật lại index của các đơn hàng còn lại trong cache
            updated_orders = OrderedDict()
            for key, value in orders.items():
                if key == ma_don: continue
                current_row_index = value["row_index"]
                if current_row_index > row_idx_to_action:
                    value["row_index"] = current_row_index - 1
                updated_orders[key] = value
            context.user_data["unpaid_orders"] = updated_orders
        
        elif action_type == "mark_paid":
            # TỐI ƯU: Thao tác trực tiếp trên sheet bằng row_index
            sheet.update_cell(row_idx_to_action, ORDER_COLUMNS["CHECK"] + 1, "False")
            await query.answer("Đã đánh dấu thanh toán.")
            orders.pop(ma_don) # Chỉ cần xóa khỏi cache, không cần cập nhật index khác

    except Exception as e:
        logger.error(f"Lỗi khi thực hiện '{action_type}' cho đơn {ma_don}: {e}")
        await query.answer(f"❌ Lỗi khi cập nhật Google Sheet.", show_alert=True)
        return

    # Điều hướng sau khi hành động thành công
    remaining_orders = context.user_data.get("unpaid_orders", OrderedDict())
    if not remaining_orders:
        await query.edit_message_text("✅ Tuyệt vời! Đã xử lý xong tất cả đơn chưa thanh toán.")
    else:
        # Đảm bảo index không bị "out of bounds"
        current_index = context.user_data.get("unpaid_index", 0)
        context.user_data["unpaid_index"] = min(current_index, len(remaining_orders) - 1)
        await show_unpaid_order(update, context, direction="stay")

async def delete_unpaid_order(update, context):
    """Callback cho nút xóa đơn."""
    ma_don = update.callback_query.data.split("|")[1].strip()
    await handle_action_and_update_view(update, context, ma_don, "delete")

async def mark_paid_unpaid_order(update, context):
    """Callback cho nút đã thanh toán."""
    ma_don = update.callback_query.data.split("|")[1].strip()
    await handle_action_and_update_view(update, context, ma_don, "mark_paid")

async def exit_unpaid(update, context):
    """Dọn dẹp và thoát về menu chính."""
    query = update.callback_query
    await query.answer()
    
    # Dọn dẹp cache
    context.user_data.pop("unpaid_orders", None)
    context.user_data.pop("unpaid_index", None)
    
    # TỐI ƯU: Gọi show_outer_menu để nó tự xử lý việc edit/thay thế tin nhắn
    await show_outer_menu(update, context)