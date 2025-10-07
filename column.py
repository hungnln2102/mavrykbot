# column.py
# Phân chia tên sheet và vị trí cột dùng chung trong toàn bộ dự án.

# =========================
# Danh sách tên Sheet
# =========================
SHEETS = {
    "ORDER": "Bảng Đơn Hàng",
    "PRICE": "Bảng Giá",          # Giữ lại để các module cũ (ví dụ view_due_orders) có thể dùng
    "SUPPLY": "Thông Tin Nguồn",
    "RECEIPT": "Biên Lai Thanh Toán",
    "REFUND": "Hoàn Tiền",
    "BANK_LIST": "Bank_List",
    "IMPORT": "Bảng Nhập Hàng",
    "EXCHANGE": "Tỷ giá",         # 👈 Sheet mới: sử dụng thay cho Bảng Giá trong add_order
}

# =========================
# Bảng Đơn Hàng
# =========================
ORDER_COLUMNS = {
    "ID_DON_HANG": 0,            # A
    "SAN_PHAM": 1,               # B
    "THONG_TIN_DON": 2,          # C
    "TEN_KHACH": 3,              # D
    "LINK_KHACH": 4,             # E
    "SLOT": 5,                   # F
    "NGAY_DANG_KY": 6,           # G
    "SO_NGAY": 7,                # H
    "HET_HAN": 8,                # I
    "CON_LAI": 9,                # J
    "NGUON": 10,                 # K
    "GIA_NHAP": 11,              # L
    "GIA_BAN": 12,               # M
    "GIA_TRI_CON_LAI": 13,       # N
    "NOTE": 14,                  # O
    "TINH_TRANG": 15,            # P
    "CHECK": 16                  # Q
}

# =========================
# (Legacy) Bảng Giá — vẫn giữ để tương thích các phần đang dùng
# =========================
PRICE_COLUMNS = {
    "TEN_SAN_PHAM": 0,       # A
    "MA_SAN_PHAM": 1,        # B
    "NGUON": 2,              # C
    "GIA_NHAP": 3,           # D
    "GIA_BAN_CTV": 4,        # E
    "GIA_BAN_LE": 5          # F
}

# =========================
# Thông Tin Nguồn
# =========================
SUPPLY_COLUMNS = {
    "TEN_NGUON": 0,              # A
    "THONG_TIN_THANH_TOAN": 1,   # B (chứa cả STK/BIN nếu bạn gộp)
    "CHU_TK": 2,                 # C
    "NGAN_HANG": 3               # D
}

# =========================
# Biên Lai Thanh Toán
# =========================
RECEIPT_COLUMNS = {
    "THOI_GIAN": 0,          # A
    "TEN_NGUON": 1,          # B
    "TONG_TIEN": 2           # C
}

# =========================
# Hoàn Tiền
# =========================
REFUND_COLUMNS = {
    "MA_DON_HANG": 0,        # A
    "NGAY_THANH_TOAN": 1,    # B
    "SO_TIEN": 2             # C
}

# =========================
# Bảng Nhập Hàng
# =========================
IMPORT_COLUMNS = {
    "ID_DON_HANG": 0,        # A
    "SAN_PHAM": 1,           # B
    "THONG_TIN_SAN_PHAM": 2, # C
    "SLOT": 3,               # D
    "NGAY_DANG_KY": 4,       # E
    "SO_NGAY_DA_DANG_KY": 5, # F
    "HET_HAN": 6,            # G
    "CON_LAI": 7,            # H
    "NGUON": 8,              # I
    "GIA_NHAP": 9,           # J
    "GIA_TRI_CON_LAI": 10,   # K
    "TINH_TRANG": 11,        # L
    "CHECK": 12              # M
}

# =========================
# Tỷ giá (sheet mới dùng trong add_order)
# Cột A, B: bỏ qua.
# C: Sản Phẩm | D: Giá CTV | E: Giá Khách | F: Check/Còn hàng | G→: mỗi cột là 1 Nguồn
# =========================
TYGIA_IDX = {
    "SAN_PHAM": 2,   # C
    "GIA_CTV": 3,    # D
    "GIA_KHACH": 4,  # E
    "STATUS": 5,     # F (TRUE = còn hàng)
    "SRC_START": 6   # G trở đi là các cột nguồn
}
