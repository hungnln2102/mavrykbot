# Phân chia các cột theo các biến
SHEETS = {
    "ORDER": "Bảng Đơn Hàng",
    "PRICE": "Bảng Giá",
    "SUPPLY": "Thông Tin Nguồn",
    "RECEIPT": "Biên Lai Thanh Toán",
    "REFUND": "Hoàn Tiền",
    "BANK_LIST": "Bank_List",
    "IMPORT": "Bảng Nhập Hàng",
}

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

# ====== BẢNG GIÁ ======
PRICE_COLUMNS = {
    "TEN_SAN_PHAM": 0,       # A
    "MA_SAN_PHAM": 1,        # B
    "NGUON": 2,              # C
    "GIA_NHAP": 3,           # D
    "GIA_BAN_CTV": 4,        # E
    "GIA_BAN_LE": 5          # F
}

# ====== THÔNG TIN NGUỒN ======
SUPPLY_COLUMNS = {
    "TEN_NGUON": 0,              # A
    "THONG_TIN_THANH_TOAN": 1,   # B (Cột này chứa cả STK và mã BIN)
    "CHU_TK": 2,                 # C
    "NGAN_HANG": 3               # D
}

# ====== BIÊN LAI THANH TOÁN ======
RECEIPT_COLUMNS = {
    "THOI_GIAN": 0,          # A
    "TEN_NGUON": 1,          # B
    "TONG_TIEN": 2           # C
}

# ====== HOÀN TIỀN ======
REFUND_COLUMNS = {
    "MA_DON_HANG": 0,        # A
    "NGAY_THANH_TOAN": 1,    # B
    "SO_TIEN": 2             # C
}

SHEETS = {
    "ORDER": "Bảng Đơn Hàng",
    "IMPORT": "Bảng Nhập Hàng",   # thêm
}

# ====== NHẬP HÀNG ======
IMPORT_COLUMNS = {
    "THOI_GIAN": 0,
    "MA_PHIEU": 1,
    "TEN_SAN_PHAM": 2,
    "MA_SAN_PHAM": 3,
    "NGUON": 4,
    "SO_LUONG": 5,
    "GIA_NHAP": 6,
    "GHI_CHU": 7
}