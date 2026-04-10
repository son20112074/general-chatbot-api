# LLM Query Service - Bản Tiếng Việt

Tài liệu này mô tả ngắn gọn cách hệ thống hoạt động và các công nghệ được sử dụng, theo hướng dễ hiểu cho người không code.

## 1. Hệ thống hoạt động như thế nào

Hệ thống hoạt động như một "bộ phiên dịch 2 bước" giữa ngôn ngữ tự nhiên và dữ liệu:

1. Người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên
   - Ví dụ: "Top khách hàng có doanh thu cao nhất quý này là ai?"

2. Hệ thống đọc cấu trúc dữ liệu (schema)
   - Tự lấy danh sách bảng và cột để hiểu dữ liệu nào đang có trong database.

3. AI tạo câu lệnh SQL dạng chỉ đọc
   - AI được hướng dẫn chỉ tạo truy vấn `SELECT/WITH`.
   - Nếu thiếu giới hạn, hệ thống tự thêm `LIMIT 1000` để tránh truy vấn quá lớn.

4. Hệ thống kiểm tra an toàn trước khi chạy SQL
   - Chặn các lệnh thay đổi dữ liệu như `INSERT`, `UPDATE`, `DELETE`, `DROP`, ...
   - Chỉ cho phép truy vấn đọc dữ liệu.

5. Hệ thống chạy SQL trên database
   - Thực thi truy vấn với timeout để tránh treo hệ thống.
   - Lấy dữ liệu trả về theo dạng dòng/cột.

6. AI chuyển kết quả thô thành câu trả lời tự nhiên
   - Dựa trên dữ liệu truy vấn được, AI viết lại thành câu trả lời ngắn gọn bằng tiếng Việt.

Kết quả cuối cùng: người dùng nhận được câu trả lời dễ đọc thay vì phải đọc bảng dữ liệu kỹ thuật.

## 2. Các lớp bảo vệ trong luồng xử lý

1. Chỉ cho phép truy vấn đọc dữ liệu.
2. Có timeout để tránh câu SQL chạy quá lâu.
3. Có kiểm tra và làm sạch SQL trước khi thực thi.
4. Mật khẩu kết nối database được lưu dưới dạng mã hóa.
5. Kết nối database được quản lý theo cơ chế tái sử dụng để ổn định và nhanh hơn.

## 3. Công nghệ đang sử dụng

1. Python + FastAPI
   - Nền tảng backend xử lý request bất đồng bộ (async), phù hợp cho tác vụ gọi AI + truy vấn DB.

2. SQLAlchemy Async Engine
   - Tạo và quản lý kết nối MySQL/PostgreSQL theo kiểu async.
   - Có connection pooling để tái sử dụng kết nối, giảm độ trễ.

3. LLM (qua OpenRouter/OpenAI-compatible endpoint)
   - Dùng mô hình ngôn ngữ để:
     1. Sinh SQL từ câu hỏi tự nhiên.
     2. Tóm tắt dữ liệu thành câu trả lời tiếng Việt.

4. LangChain BaseChatModel Wrapper
   - Một lớp "adapter" giúp client LLM nội bộ hoạt động theo chuẩn giao tiếp của LangChain.
   - Chuẩn hóa input/output giữa prompt và phản hồi từ model.

5. Regex + Rule-based SQL guard
   - Dùng biểu thức chính quy để trích xuất SQL từ phản hồi AI.
   - Dùng luật chặn từ khóa nguy hiểm để giảm rủi ro.

6. Cryptography (Fernet + PBKDF2)
   - Mã hóa/giải mã mật khẩu kết nối database.
   - Giảm rủi ro lộ thông tin nhạy cảm khi lưu trữ.

## 4. Tóm tắt dễ hiểu

Có thể hình dung hệ thống như sau:

1. AI thứ nhất: hiểu câu hỏi và viết SQL an toàn.
2. Database: trả dữ liệu thật.
3. AI thứ hai: diễn giải dữ liệu thành tiếng Việt tự nhiên.

Mục tiêu chính: giúp người dùng hỏi dữ liệu bằng ngôn ngữ thường ngày, nhưng vẫn giữ tính an toàn và kiểm soát kỹ thuật ở tầng backend.
