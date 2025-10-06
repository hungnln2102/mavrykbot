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
    "ID_DON_HANG": 0,
    "SAN_PHAM": 1,
    "THONG_TIN_DON": 2,
    "TEN_KHACH": 3,
    "LINK_KHACH": 4,
    "SLOT": 5,
    "NGAY_DANG_KY": 6,
    "SO_NGAY": 7,
    "HET_HAN": 8,
    "CON_LAI": 9,
    "NGUON": 10,
    "GIA_NHAP": 11,
    "GIA_BAN": 12,
    "GIA_TRI_CON_LAI": 13,
    "NOTE": 14,
    "TINH_TRANG": 15,
    "CHECK": 16
}

# ====== BẢNG GIÁ ======
PRICE_COLUMNS = {
    "TEN_SAN_PHAM": 0,
    "MA_SAN_PHAM": 1,
    "NGUON": 2,
    "GIA_NHAP": 3,
    "GIA_BAN_CTV": 4,
    "GIA_BAN_LE": 5
}

# ====== THÔNG TIN NGUỒN ======
SUPPLY_COLUMNS = {
    "TEN_NGUON": 0,
    "THONG_TIN_THANH_TOAN": 1,
    "CHU_TK": 2,
    "NGAN_HANG": 3
}

# ====== BIÊN LAI THANH TOÁN ======
RECEIPT_COLUMNS = {
    "THOI_GIAN": 0,
    "TEN_NGUON": 1,
    "TONG_TIEN": 2
}

# ====== HOÀN TIỀN ======
REFUND_COLUMNS = {
    "MA_DON_HANG": 0,
    "NGAY_THANH_TOAN": 1,
    "SO_TIEN": 2
}

# ====== NHẬP HÀNG ======
IMPORT_COLUMNS = {
    "ID_DON_HANG": 0,
    "SAN_PHAM": 1,
    "THONG_TIN_SAN_PHAM": 2,
    "SLOT": 3,
    "NGAY_DANG_KY": 4,
    "SO_NGAY_DA_DANG_KY": 5,
    "HET_HAN": 6,
    "CON_LAI": 7,
    "NGUON": 8,
    "GIA_NHAP": 9,
    "GIA_TRI_CON_LAI": 10,
    "TINH_TRANG": 11,
    "CHECK": 12
}