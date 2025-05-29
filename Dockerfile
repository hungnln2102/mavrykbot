# Sử dụng image Python chính thức
FROM python:3.11-slim


# Thiết lập thư mục làm việc
WORKDIR /app

# Copy toàn bộ mã nguồn vào image
COPY . .

# Cài đặt các package cần thiết
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Thiết lập biến môi trường nếu dùng .env (hoặc copy riêng file token.env nếu cần)
# ENV PYTHONUNBUFFERED=1

# Chạy bot (thay main.py thành file khởi động bot của bạn)
CMD ["python", "main.py"]
