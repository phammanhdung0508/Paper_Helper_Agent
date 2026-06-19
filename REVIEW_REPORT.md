# Báo cáo Review Kiến trúc & Mã nguồn: Paper Helper & Visual Study Companion

**Người thực hiện:** Principal AI Engineer & Software Architect
**Ngày thực hiện:** 2024-05-23
**Ngôn ngữ:** Tiếng Việt

---

## 1. Tóm tắt Kiến trúc Hiện tại

Hệ thống được xây dựng theo mô hình **Multi-Agent** sử dụng **LangGraph** để điều hướng và **Gradio** làm giao diện người dùng.

- **Entrypoints:** `main.py` (khởi chạy server và DB).
- **Luồng xử lý chính:**
    - Chat: Router (LLM-based) phân loại ý định người dùng thành `general` (tán gẫu) hoặc `rag` (tra cứu tài liệu).
    - Study: Trích xuất Concept Graph, tạo Visual Spec và đánh giá Mastery thông qua các Agent riêng biệt.
- **Thành phần LangChain:** Sử dụng `StateGraph` để quản lý luồng hội thoại, `ChatOpenAI` cho các node, và `MemorySaver` cho checkpointing.
- **Dữ liệu:** SQLite lưu trữ metadata, history, và journal. Chroma DB lưu trữ vector embeddings cho RAG.
- **Observability:** Tích hợp Langfuse qua `CallbackHandler` và gọi trực tiếp SDK để log metadata/feedback.

---

## 2. Review chi tiết theo nhóm

### A. Kiến trúc tổng thể & Khả năng mở rộng
- **Hiện trạng:** Các Agent phụ trợ (`ConceptGraphAgent`, `VisualSandboxAgent`, `MasteryEvaluatorAgent`) đang hoạt động độc lập với luồng chính của LangGraph.
- **Đánh giá:** Kiến trúc bị phân mảnh. Việc gọi trực tiếp các agent này từ UI làm mất đi khả năng trace đồng nhất trên Langfuse và khó quản lý trạng thái phức tạp.

### B. Thiết kế Agent & Tool Usage
- **Hiện trạng:** Node RAG gọi trực tiếp hàm DB/VectorStore.
- **Đánh giá:** Chưa tận dụng được sức mạnh của **LangChain Tools**. Việc hardcode logic lấy dữ liệu vào node làm giảm khả năng linh hoạt nếu muốn chuyển đổi model hoặc thêm các nguồn dữ liệu khác.

### C. Prompt Engineering
- **Hiện trạng:** Prompt nằm rải rác trong code Python (`app/agents.py`, `app/graph.py`).
- **Đánh giá:** Khó quản lý phiên bản, khó thử nghiệm prompt mới mà không phải deploy lại code.

### D. Error Handling, Retry & Fallback
- **Hiện trạng:** Trước khi fix, các lời gọi LLM không có cơ chế retry. Hiện đã được bổ sung `max_retries=3`.
- **Đánh giá:** Vẫn thiếu cơ chế fallback nâng cao (ví dụ: đổi sang model rẻ hơn/nhanh hơn khi model chính gặp lỗi).

### E. Observability với Langfuse
- **Hiện trạng:** Sử dụng cả `CallbackHandler` và gọi `Langfuse()` SDK thủ công.
- **Đánh giá:** Tốt cho việc capturing feedback, nhưng cần chuẩn hóa để tránh dư thừa dữ liệu trace.

### F. Security
- **Hiện trạng:** Ứng dụng có chức năng ghi đè file `.env` từ giao diện người dùng.
- **Đánh giá:** **Rủi ro nghiêm trọng**. Production app không bao giờ nên có quyền ghi vào file cấu hình của chính nó. Ngoài ra, việc dùng SQLite vẫn tiềm ẩn rủi ro injection nếu không dùng parameterized queries triệt để.

---

## 3. Các vấn đề phát hiện và Cách sửa cụ thể

### Vấn đề 1: Ghi đè file cấu hình hệ thống từ UI
- **Mức độ:** **Critical**
- **File:** `app/ui.py`, hàm `handle_save_config`.
- **Mô tả:** Cho phép cập nhật OpenAI API Key bằng cách ghi trực tiếp vào `.env`.
- **Vì sao đây là vấn đề:** Rủi ro bảo mật nghiêm trọng. Nếu hacker chiếm quyền UI, họ có thể ghi đè các cấu hình nhạy cảm khác. Trong môi trường Docker/Cloud, file system thường là read-only hoặc không nên bị thay đổi động.
- **Cách sửa:** Chuyển sang quản lý cấu hình bằng Environment Variables thực thụ. API Key nên được người dùng nhập vào mỗi session (lưu trong memory/state) thay vì lưu vĩnh viễn vào server file.
- **Ví dụ code:**
  ```python
  # Thay vì lưu vào .env, hãy lưu vào Gradio Session State hoặc LangGraph State
  def update_session_key(api_key, profile):
      profile.api_key = api_key
      return "Key updated for this session."
  ```

### Vấn đề 2: Thiếu tính nhất quán trong quản lý State
- **Mức độ:** **High**
- **File:** `app/graph.py` và `app/database.py`.
- **Mô tả:** Hội thoại được lưu đồng thời trong `MemorySaver` của LangGraph và bảng `chat_messages` của SQLite.
- **Vì sao đây là vấn đề:** Dễ xảy ra lệch dữ liệu (out-of-sync). Nếu LangGraph checkpoint thất bại nhưng DB vẫn lưu (hoặc ngược lại), lịch sử hội thoại sẽ bị sai lệch.
- **Cách sửa:** Sử dụng một giải pháp lưu trữ duy nhất. Có thể implement một `BaseCheckpointSaver` tùy chỉnh cho LangGraph để lưu trực tiếp vào SQLite của dự án.

### Vấn đề 3: Rủi ro SQL Injection
- **Mức độ:** **Medium**
- **File:** `app/database.py`, hàm `save_concepts`.
- **Mô tả:** Sử dụng string formatting hoặc logic phức tạp trong query.
- **Cách sửa:** Luôn dùng dấu `?` của thư viện `sqlite3`.
- **Ví dụ code:**
  ```python
  cursor.execute("INSERT OR REPLACE INTO concepts (...) VALUES (?, ?, ...)", values)
  ```

### Vấn đề 4: Phụ thuộc vào model GPT-4o-mini cố định
- **Mức độ:** **Low**
- **Mô tả:** Tất cả agents đều hardcode model name.
- **Cách sửa:** Đưa model name vào file cấu hình.

---

## 4. Những phần đang làm tốt
- **UX/UI:** Giao diện Gradio được đầu tư thẩm mỹ (glassmorphic), phản hồi mượt mà.
- **Grounded RAG:** Prompt cho RAG Agent rất chặt chẽ, yêu cầu dẫn chứng số trang và tránh hallucination tốt.
- **Mastery Logic:** Cơ chế Monotone Clamp (điểm không giảm) là một thiết kế thông minh cho giáo dục.
- **Observability:** Việc tích hợp Langfuse ngay từ đầu giúp dự án có khả năng debug rất tốt.

---

## 5. Danh sách ưu tiên sửa đổi
1. **Ưu tiên 1:** Loại bỏ tính năng ghi file `.env` từ UI. Chuyển sang dùng biến môi trường hoặc Vault.
2. **Ưu tiên 2:** Tham số hóa (Parameterize) toàn bộ các câu lệnh SQL.
3. **Ưu tiên 3:** Refactor các Agent (Concept, Visual, Mastery) thành các node trong LangGraph.
4. **Ưu tiên 4:** Chuyển prompt ra các file config hoặc Langfuse Prompt Management.

---

## 6. Checklist Production-Readiness
- [ ] **Bảo mật:** Loại bỏ quyền ghi vào file hệ thống. Sử dụng HTTPS cho Gradio.
- [ ] **Độ tin cậy:** Triển khai cơ chế retry (Đã làm một phần). Thêm Circuit Breaker nếu gọi nhiều dịch vụ ngoài.
- [ ] **Hiệu năng:** Chunking PDF lớn có thể gây lag, cần chuyển sang xử lý Background Jobs (Celery/Redis).
- [ ] **Chi phí:** Thêm giới hạn Token sử dụng cho mỗi User/Session trên Langfuse.
- [ ] **Hạ tầng:** Dockerize toàn bộ ứng dụng (hiện tại mới chỉ Dockerize Langfuse).

---

## 7. Đề xuất bộ Test/Eval tối thiểu
1. **RAG Faithfulness:** Kiểm tra câu trả lời có thực sự nằm trong context không (dùng Langfuse Evals).
2. **Relevancy:** Câu trả lời có đúng trọng tâm câu hỏi không.
3. **Mastery Unit Test:** Test trường hợp student trả lời sai nhưng điểm mastery vẫn không được giảm (Monotone property).
4. **Router Accuracy:** Test với 100 câu hỏi mẫu để tính F1-score cho việc phân loại `general` vs `rag`.
