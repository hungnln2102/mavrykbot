# app/update_states.py

"""
Định nghĩa các hằng số trạng thái (states) cho ConversationHandler
của chức năng cập nhật đơn hàng (update_order).

Việc tách ra file riêng giúp tránh lỗi Circular Import.
"""

# --- TRẠNG THÁI (STATES) CHO UPDATE_ORDER CONVERSATION ---
(
    SELECT_MODE,         # Chọn chế độ tìm kiếm (Mã đơn / Thông tin SP)
    INPUT_VALUE,         # Chờ nhập giá trị tìm kiếm
    SELECT_ACTION,       # Hiển thị đơn hàng, chờ chọn hành động (Sửa, Xóa, Gia hạn, Next/Prev)
    EDIT_CHOOSE_FIELD,   # Chờ chọn trường cần sửa
    EDIT_INPUT_SIMPLE,   # Chờ nhập giá trị mới cho các trường đơn giản
    EDIT_INPUT_SAN_PHAM, # Chờ nhập giá trị mới cho trường Sản Phẩm
    EDIT_INPUT_NGUON,    # Chờ nhập giá trị mới cho trường Nguồn
    EDIT_INPUT_NGAY_DK,  # Chờ nhập giá trị mới cho trường Ngày Đăng Ký
    EDIT_INPUT_SO_NGAY,  # Chờ nhập giá trị mới cho trường Số Ngày
    EDIT_INPUT_TEN_KHACH,# Chờ nhập giá trị mới cho trường Tên Khách
    EDIT_INPUT_LINK_KHACH # Chờ nhập giá trị mới cho trường Link Khách (sau khi nhập Tên Khách)
) = range(11)