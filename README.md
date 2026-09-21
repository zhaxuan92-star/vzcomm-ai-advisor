# Vzcomm AI Advisor

Trợ lý Flask cho quốc gia NationStates, dùng NationStates API để đọc Issues và Gemini để phân tích lựa chọn.

## Có gì trong bản hiện tại

- Đọc Issues của quốc gia qua NationStates API.
- Phân tích từng Issue bằng Gemini.
- Có nút mở thẳng trang NationStates của quốc gia.
- Có endpoint `/health` để kiểm tra server.
- Sửa lỗi URL API bị chèn Markdown.
- Tắt Flask debug mode khi chạy production.
- Gemini model được cấu hình bằng `GEMINI_MODEL` và mặc định là `gemini-3.6-flash`.

Gemini 3.6 Flash hiện là model ổn định và có hỗ trợ structured output/function calling theo tài liệu Google AI. 

## Biến môi trường

Tạo các biến môi trường trên máy chủ:

```text
FLASK_SECRET_KEY=<chuỗi ngẫu nhiên dài>
GEMINI_API_KEY=<API key>
GEMINI_API_KEY_2=<API key dự phòng, tùy chọn>
GEMINI_MODEL=gemini-3.6-flash
NS_CONTACT=Vzcomm AI Advisor; contact: your-email@example.com
```

Không commit API key, mật khẩu NationStates hoặc token X-Autologin vào Git.

## Chạy

```bash
pip install -r requirements.txt
python app.py
```

Production nên chạy bằng Gunicorn hoặc máy chủ WSGI tương đương.

## Lưu ý bảo mật

Ứng dụng hiện dùng Flask session và credential NationStates để gọi private API. Nếu triển khai cho nhiều người dùng, nên chuyển credential storage sang server-side session store/secret manager thay vì lưu credential trong process hoặc client session.

Không bật Flask debug mode trên server công khai.

## Quy trình đề xuất

1. Đăng nhập vào dashboard.
2. Kiểm tra danh sách Issue.
3. Xem phân tích AI.
4. Chỉ gửi lựa chọn sau khi người dùng xác nhận.

NationStates có rate limit và yêu cầu User-Agent có thông tin nhận diện. Hãy tuân thủ API Terms của NationStates khi triển khai.
