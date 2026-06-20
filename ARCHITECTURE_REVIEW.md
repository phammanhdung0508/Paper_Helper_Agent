# 🏗 Báo Cáo Review Kiến Trúc - Dự Án "Paper Helper & Visual Study Companion" (Cập Nhật)

**Vai trò:** Principal AI Engineer / Software Architect
**Mục tiêu:** Đánh giá khắt khe theo chuẩn Production doanh nghiệp, tập trung dọn đường cho phiên bản chuyển đổi kiến trúc sang **Next.js (Frontend) + FastAPI (Backend)** theo định hướng thực tế.
**Ghi chú:** Bản báo cáo này đã được cập nhật dựa trên những thay đổi gần đây nhất (bổ sung `max_retries=3` cho các LLM calls và sửa đổi logic lưu API Key).

---

## 1. Tóm tắt Kiến Trúc Hiện Tại (Mental Map)

- **Entrypoint:** `main.py` khởi tạo SQLite, nạp data mock mặc định, và bật UI Gradio.
- **Frontend / UI Layer:** `app/ui.py` chạy bằng **Gradio**. Đây là một monolithic UI, gắn chặt xử lý giao diện với việc gọi backend logic.
- **Agent / Logic Layer:**
  - `app/graph.py`: Dùng **LangGraph** quản lý luồng hội thoại chat qua `AgentState`, điều hướng bằng `Router` sang `General Agent` hoặc `RAG Agent`.
  - `app/agents.py`: Chứa các Agent thực hiện tác vụ độc lập (tạo Graph khái niệm, sinh spec Visualization, đánh giá điểm Mastery) dùng `ChatOpenAI` kết hợp `Structured Output` (Pydantic).
- **Data / State Layer:**
  - `app/database.py`: Sử dụng **SQLite** lưu trữ file, page, concept, messages (raw SQL, không ORM).
  - Sử dụng **Chroma** làm Vector Database cục bộ cho RAG.
  - Quản lý state LangGraph bằng **in-memory** `MemorySaver`.
- **Observability Layer:** **Langfuse** được tích hợp qua Callback cho LangGraph để trace `router` và `rag/general` agent.

---

## 2. Các Nhận Xét Ưu Điểm (Phần đang làm tốt)

1. **Sử dụng Pydantic cho Structured Output:** Việc định nghĩa các Schema rõ ràng như `KnowledgeGraph`, `MasteryAssessment` để parse JSON từ LLM là một Best Practice rất xuất sắc trong Production.
2. **Thiết kế System Prompts:** Các prompt được viết chi tiết, có định hướng RAG strict (VD: bắt buộc trích xuất số trang `[Page X]` và từ chối nếu không có trong context).
3. **Phân tách Agent Tasks:** Chia nhỏ tác vụ phức tạp (Concept Spotting, Visual Planner, Evaluator) thay vì gộp chung vào 1 siêu agent giúp dễ scale và debug.
4. **Langfuse Integration:** Việc setup Docker Compose và áp dụng Langfuse tracing là bước đầu tư tốt cho Observability.
5. **Cập nhật Resilience Kịp Thời:** Việc vừa bổ sung tham số `max_retries=3` cho toàn bộ các node gọi `ChatOpenAI` đã giải quyết được nguy cơ treo request khi OpenAI API bị Rate Limit.

---

## 3. Chi Tiết Các Vấn Đề Và Cải Tiến Theo Chuẩn Production

### Nhóm 1: Security (Bảo mật & Rủi ro hệ thống)

**1. Lỗ hổng ghi đè biến môi trường (Secrets) qua UI (Đã sửa một phần, nhưng vẫn còn rủi ro)**
- **Mức độ:** **High** (Đã giảm từ Critical do dùng thư viện `dotenv` an toàn hơn)
- **File:** `app/ui.py` (Hàm `handle_save_config`)
- **Mô tả:** Ứng dụng hiện tại đã sử dụng hàm `set_key` của `dotenv` để cập nhật cấu hình API.
- **Vì sao là vấn đề:** Trong môi trường Production (như Docker/Kubernetes container), hệ thống file thường là read-only (hoặc ephemeral). Việc cho phép ứng dụng tự sửa đổi tệp `.env` của chính nó vẫn vi phạm nguyên tắc bảo mật và kiến trúc cloud-native.
- **Cách sửa:** Xoá bỏ hoàn toàn việc chỉnh sửa file `.env`. API Key cần được quản lý qua AWS Secrets Manager / HashiCorp Vault. Trong trường hợp ứng dụng là dạng "Bring Your Own Key", hãy lưu giữ token trong session tạm thời (ví dụ: LocalStorage ở Frontend Next.js truyền xuống qua HTTP Authorization header), chứ không lưu vào server disk.

**2. Rủi ro SQL Injection (Thiếu ORM)**
- **Mức độ:** **Medium / High**
- **File:** `app/database.py`
- **Mô tả:** Sử dụng raw SQL với thư viện `sqlite3`. Dù đã dùng parameter binding (`?`), việc quản lý schema thủ công và nối chuỗi rất dễ dẫn đến sai sót khi dự án lớn dần.
- **Cách sửa:** Chuyển sang ORM. Khi viết lại bằng FastAPI, hãy dùng **SQLAlchemy** (hoặc **SQLModel**). Nếu Next.js làm fullstack có thể dùng **DrizzleORM**.

**3. Thiếu cơ chế Xác thực (Auth) và Phân ranh giới dữ liệu (Multi-tenancy)**
- **Mức độ:** **High**
- **File:** `app/database.py`, `app/ui.py`
- **Mô tả:** Không có session an toàn. Bất kỳ ai vào web cũng có thể đọc, xoá file của người khác do `session_id` chỉ tạo tạm bằng UUID Frontend mà không có đăng nhập xác thực.
- **Cách sửa:** Khi sang Next.js/FastAPI, phải dùng **JWT (OAuth2)**. Mọi truy vấn DB phải kèm theo điều kiện `WHERE user_id = ?` để cô lập không gian làm việc.

**4. Rủi ro Prompt Injection**
- **Mức độ:** **High**
- **File:** `app/graph.py`
- **Mô tả:** Câu hỏi của User được đưa thẳng vào `messages` của LLM. Người dùng có thể bẻ khóa RAG Agent bằng cách nhập các lệnh can thiệp logic (Jailbreak).
- **Cách sửa:** Thêm bước Guardrails (như NeMo Guardrails) trước khi truyền vào LangGraph node, hoặc sử dụng Prompt Sanitization.

### Nhóm 2: Architecture Tổng thể & Trạng thái (Định hướng Next.js / FastAPI)

**1. Tràn RAM do In-memory LangGraph Checkpointer**
- **Mức độ:** **High**
- **File:** `app/graph.py` (`memory = MemorySaver()`)
- **Mô tả:** `MemorySaver` lưu toàn bộ tin nhắn chat trong RAM của Python process. Với số lượng session lớn, Server sẽ sập do Out Of Memory (OOM) và dữ liệu state bị reset mỗi khi restart server.
- **Cách sửa:** Cần phải thay thế `MemorySaver` bằng `AsyncPostgresSaver` hoặc `RedisSaver` (các persistence tools của LangGraph).

**2. Monolithic UI (Trộn lẫn Giao diện & Xử lý)**
- **Mức độ:** **High**
- **File:** `app/ui.py`, `main.py`
- **Mô tả:** Logic Gradio gọi trực tiếp DB và gọi LLM blocking.
- **Cách sửa:** Tách làm 2 lớp (như định hướng dự án):
  - **FastAPI Layer:** Cung cấp API (REST / WebSocket / Server-Sent Events).
  - **Next.js Layer:** Chỉ gọi API và vẽ giao diện UI.

### Nhóm 3: Performance, Latency và Cost

**1. Tắc nghẽn do Xử lý PDF Đồng bộ (Blocking Ingestion)**
- **Mức độ:** **High**
- **File:** `app/database.py` (Hàm `ingest_document`)
- **Mô tả:** Quá trình đọc file PDF, chunking, nhúng Embeddings bằng Chroma block hoàn toàn UI. File lớn sẽ làm sập kết nối HTTP.
- **Cách sửa:** Đẩy các tác vụ nặng vào Queue (Celery + Redis / FastAPI BackgroundTasks) và trả về HTTP 202 ngay lập tức. Frontend sẽ polling để lấy trạng thái xử lý.

**2. Token Bloat khi trích xuất Graph**
- **Mức độ:** **Medium**
- **File:** `app/agents.py` (`ConceptGraphAgent.build_graph`)
- **Mô tả:** Đẩy nguyên chuỗi 25.000 ký tự vào `gpt-4o-mini`.
- **Cách sửa:** Sử dụng chiến lược **Map-Reduce** (chia PDF thành chunk, trích xuất song song, rồi gom lại) để LLM tập trung tốt hơn và tránh bị Lost-in-the-middle.

### Nhóm 4: Observability & Prompt Engineering

**1. Tracing Langfuse bị khuyết thiếu (Incomplete Tracing)**
- **Mức độ:** **Medium**
- **File:** `app/agents.py`, `app/database.py`
- **Mô tả:** Chỉ LangGraph workflow là có Tracing. Các Agent tốn kém và quan trọng khác (như `ConceptGraphAgent`, `VisualSandboxAgent`, RAG Retrieval Logic) chạy ngầm không được đo lường Token.
- **Cách sửa:** Thêm thư viện `langfuse` vào `app/agents.py` và bọc các class methods sinh token bằng decorator `@observe()`.

**2. Hardcode Prompts lẫn trong Python Code**
- **Mức độ:** **Medium**
- **File:** Rải rác khắp code.
- **Cách sửa:** Chuyển qua sử dụng tính năng **Prompt Management** của Langfuse.

---

## 4. Đề xuất Bộ Test & Eval Cho Agent (Sẵn sàng Production)

Để tự tin deploy, dự án cần xây dựng Evaluation Pipeline:

1. **RAG Evaluation (Đánh giá RAG):**
   - Công cụ: **Ragas** hoặc **TruLens**.
   - Đo lường: *Context Precision*, *Context Recall*, *Answer Faithfulness*.
2. **Agent / Tool Evaluation:**
   - Tạo bộ test case tự động cho từng hàm Schema Output (ví dụ Output JSON của Concept extraction có đúng cấu trúc Node-Edge không).
3. **End-to-end Tracing & User Feedback:**
   - Tạo cronjob tổng hợp các log Feedback 👍/👎 từ Langfuse để đánh giá chất lượng phiên bản mô hình hiện tại.

---

## 5. Checklist Mức Ưu Tiên Hành Động (Next Steps)

🔥 **Phase 1: Vá lổ hổng & Ổn định nền tảng (Immediate)**
- [x] Đã cấu hình Retry (`max_retries`) cho `ChatOpenAI`.
- [ ] Gỡ bỏ hoàn toàn logic chỉnh sửa `.env` từ code backend; chuyển sang đọc API Token từ memory/request header.
- [ ] Thay thế `MemorySaver` trong `app/graph.py` bằng giải pháp Persistence (SQL/Redis).
- [ ] Thêm decorator `@observe()` của Langfuse vào các module còn lại (`app/agents.py`).

🚀 **Phase 2: Chuyển đổi Kiến trúc (Migration)**
- [ ] Dựng REST API bằng FastAPI.
- [ ] Xây dựng Frontend UI bằng Next.js + React Flow (cho Knowledge Graph).

💎 **Phase 3: Tối ưu Performance & Scale**
- [ ] Tách việc Parse và Embed PDF thành Background Task.
- [ ] Sử dụng SQLAlchemy (hoặc Drizzle ORM) thay cho Raw SQLite.
- [ ] Đẩy System Prompts lên Langfuse Prompt Management.

*Báo cáo kết thúc.*
