# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns tìm thấy trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong mã nguồn (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub sẽ lộ secret ngay lập tức.
2. **Hardcode cấu hình (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` không đọc từ biến môi trường, muốn đổi cấu hình cho staging/production phải sửa code.
3. **Dùng `print()` và log lộ secret (dòng 33–34, 38):** `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó thu thập/lọc log trên production, vừa làm rò rỉ API key ra log.
4. **Thiếu Health Check endpoint (dòng 42–43):** Không có `/health` hay `/ready`, nên cloud platform hoặc load balancer không biết app còn sống hay đã treo để tự restart.
5. **Bind `localhost`, cứng port và bật `reload=True` (dòng 51–53):** `host="localhost"` không nhận được traffic từ ngoài container; `port=8000` cố định không nhận `PORT` động từ Railway/Render; `reload=True` gây tốn tài nguyên và không an toàn trên production.
6. **Không xử lý Graceful Shutdown:** Không có `lifespan` hay handler bắt tín hiệu `SIGTERM`, nên khi server bị tắt/restart giữa chừng, các request đang xử lý dở sẽ bị cắt ngang đột ngột.

### Exercise 1.2: Kết quả chạy bản `develop`

- Chạy `python app.py` trên cổng `8000` và gọi bằng query parameter:
```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```
- Bản `develop` trả về `200 OK` dạng `{"answer": "..."}`, nhưng ở terminal server bị lộ dòng `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`.

### Exercise 1.3: So sánh `develop/app.py` và `production/app.py`

| Feature | Basic (`develop/app.py`) | Advanced (`production/app.py`) | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Config & Secrets** | Hardcode trực tiếp trong code (dòng 17–22) | Đọc từ biến môi trường qua `config.py` / `.env` (dòng 24) | Bảo mật secret (không đẩy lên Git), đổi cấu hình theo từng môi trường (dev/staging/prod) không cần sửa code |
| **Health check** | Không có | Có `GET /health` (dòng 135) và `GET /ready` (dòng 152) | Platform/Orchestrator biết container còn sống (`/health`) và đã sẵn sàng nhận traffic chưa (`/ready`) |
| **Logging** | `print()` tự do, in cả secret (dòng 33–34) | Structured JSON logging (dòng 28–31), không log secret | Các hệ thống log tập trung (Datadog, Loki) dễ parse/truy vấn theo JSON field và đảm bảo an toàn thông tin |
| **Shutdown** | Tắt đột ngột | `lifespan` (dòng 39–67) đặt `is_ready = False`, chờ request xong + `SIGTERM` handler (dòng 180–189) | Tránh cắt ngang request của người dùng đang xử lý dở khi deploy bản mới hoặc scale down |
| **Host & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (env `PORT`), `reload=settings.debug` (dòng 196–198) | Container cần `0.0.0.0` để nhận request từ bên ngoài, cloud cấp `PORT` động qua biến môi trường |

- Kết quả test bản `production` (`POST /ask` nhận JSON body):
```json
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

---

## Part 2: Docker

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (bản đầy đủ ~1 GB, chứa nhiều công cụ hệ thống không cần thiết khi chạy thật).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY app.py`?** Để tận dụng **Docker layer cache**. `requirements.txt` ít khi thay đổi; khi sửa code `app.py` và build lại, Docker tái sử dụng cache của layer `pip install` thay vì cài lại thư viện từ đầu.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh mặc định khi container khởi động và **có thể bị ghi đè hoàn toàn** nếu truyền lệnh mới lúc `docker run`.
   - `ENTRYPOINT` định nghĩa lệnh cố định luôn chạy của container; tham số truyền thêm lúc `docker run` sẽ được nối vào làm đối số cho `ENTRYPOINT`.

### Exercise 2.2: Build & chạy container `my-agent:develop`

- Build từ gốc repo và chạy map port `1234:8000`, gọi `POST /ask?question=What%20is%20Docker%3F` trả về `200 OK`.

### Exercise 2.3: So sánh kích thước Multi-stage build

- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` để compile và cài Python packages vào `/root/.local`.
- **Stage 2 (`runtime`):** Dùng `python:3.11-slim` sạch, chỉ `COPY --from=builder` thư mục `/root/.local` và source code sang, chạy bằng user non-root `appuser` và gắn `HEALTHCHECK`. Toàn bộ công cụ build (`gcc`, `libpq-dev`, cache) được bỏ lại ở Stage 1.
- **Kích thước đo thực tế (`docker images | grep my-agent`):**
  - `my-agent:develop`: **1.67 GB** (~1,670 MB)
  - `my-agent:advanced`: **240 MB**
  - **Chênh lệch:** Giảm **85.6%** dung lượng.

### Exercise 2.4: Docker Compose stack

- **Các services & cách giao tiếp (qua bridge network `internal`):**
  ```text
  Client ──(port 80)──▶ Nginx (reverse proxy) ──▶ Agent (FastAPI :8000)
                                                    ├──▶ Redis (:6379)
                                                    └──▶ Qdrant (:6333)
  ```
  `agent` không expose port trực tiếp ra ngoài, chỉ nhận traffic qua `nginx`, và `depends_on` `redis` + `qdrant` ở trạng thái `service_healthy`.
- **Kết quả test qua Nginx:**
  - `GET http://localhost/health`:
    `{"status":"ok","uptime_seconds":95.5,"version":"2.0.0","timestamp":"2026-11-25T10:03:12.575235"}`
  - `POST http://localhost/ask`:
    `{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}`

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`) & So sánh `railway.toml` vs `render.yaml`

- **Public URL:** https://agent-production-9bf6a6c9.up.railway.app
- **Chi tiết & lệnh test:** xem [DEPLOYMENT.md](DEPLOYMENT.md)
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

**So sánh `railway.toml` và `render.yaml`:**

| Tiêu chí | `railway.toml` | `render.yaml` (Blueprint) |
| :--- | :--- | :--- |
| **Định dạng & Mục tiêu** | File TOML ngắn gọn, cấu hình cho **1 service** (`[build]`, `[deploy]`). | File YAML dạng Infrastructure-as-Code (Blueprint), khai báo được **cả stack nhiều service** (`services:`, database/Redis...). |
| **Cách chỉ định Docker** | `[build] builder = "DOCKERFILE"` | `type: web` + `runtime: docker` (tự tìm `Dockerfile`). |
| **Health check** | `healthcheckPath = "/health"` dưới mục `[deploy]`. | `healthCheckPath: /health` dưới từng service. |
| **Biến môi trường & Secret** | Thường đặt biến môi trường (`AGENT_API_KEY`, `REDIS_URL`) trực tiếp qua Railway Dashboard hoặc `railway variables set` chứ không khai báo trong `railway.toml`. | Cho phép khai báo ngay danh sách `envVars:` trong file; với secret phải dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên dashboard, không lộ vào Git). |

### Exercise 3.3: Mô tả CI/CD pipeline Cloud Run (`cloudbuild.yaml` & `service.yaml`)

Pipeline trong `03-cloud-deployment/production-cloud-run/` tự động chạy khi push code lên nhánh `main` qua 4 bước tuần tự (`waitFor`):
1. **Step 1 (`test`):** Dùng container `python:3.11-slim` cài dependencies và chạy `pytest tests/ -v`; nếu test fail thì dừng pipeline ngay.
2. **Step 2 (`build`):** Dùng `cloud-builders/docker` build Docker image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from` để build nhanh hơn).
3. **Step 3 (`push`):** Đẩy cả 2 tag image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Step 4 (`deploy`):** Dùng `gcloud run deploy` triển khai image vừa build lên Cloud Run (`asia-southeast1`), cấu hình autoscale (`min=1`, `max=10`), tài nguyên (`512Mi` RAM, `1` CPU), và nạp secret từ **Secret Manager** (`--set-secrets`) chứ không hardcode. File `service.yaml` (chuẩn Knative) mô tả chi tiết cấu hình Service đó dưới dạng IaC, gồm `livenessProbe` (`/health`), `startupProbe` (`/ready`) và giới hạn concurrency `80` req/instance.

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả test `curl -i` (401 / 200 / 429)

- **401 Unauthorized (thiếu API Key ở `04-api-gateway/develop`):**
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

- **200 OK (đăng nhập `POST /auth/token` với `student`/`demo123`, dùng `Authorization: Bearer <TOKEN_MASKED>` ở `04-api-gateway/production`):**
```http
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"Sample 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":8,"budget_remaining_usd":4.2e-05}}
```

- **429 Too Many Requests (gọi vượt ngưỡng 10 req/phút của `student`):**
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.3 & 4.4: Giải thích Rate Limiting & Cost Guard

- **Rate Limiter (`rate_limiter.py`):** Dùng thuật toán **Sliding Window Counter** (lưu timestamp các request trong 60 giây gần nhất bằng `deque`). Tài khoản thường giới hạn `10 req/phút` (`rate_limiter_user`), còn `admin` được `100 req/phút` (`rate_limiter_admin`). Rate limit bảo vệ **tốc độ gọi API** (chống spam/DDoS).
- **Cost Guard (`cost_guard.py`):** Kiểm tra tổng chi phí token trước khi gọi LLM (`check_budget`): nếu vượt ngân sách ngày của user thì trả **`402 Payment Required`**, vượt ngân sách toàn hệ thống trả **`503`**. Sau khi LLM trả lời, `record_usage` tính tiền theo giá input/output tokens và cộng dồn.
- **Tại sao cần cả Rate Limit lẫn Cost Guard?** Rate limit giới hạn *số lượng request/phút*, còn Cost Guard giới hạn *tổng tiền tiêu thụ* (vì một vài request có prompt/output rất dài vẫn có thể gây tốn nhiều tiền dù chưa chạm rate limit). Trong production (Part 6), cả hai đều phải lưu state trong **Redis** (như `ZSET` và `INCRBYFLOAT`) thay vì RAM để không mất khi restart hoặc scale nhiều instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Liveness vs Readiness, Graceful Shutdown & Stateless Design

- **`/health` (Liveness) vs `/ready` (Readiness):**
  - `/health`: Kiểm tra process của agent còn sống hay không (luôn trả `200` khi process chạy, kể cả khi Redis chưa sẵn sàng). Nếu fail → platform restart container.
  - `/ready`: Kiểm tra agent đã sẵn sàng nhận traffic chưa (ping Redis/DB thành công → `200`, mất kết nối → `503`). Load balancer dựa vào `/ready` để tạm ngừng đẩy traffic vào instance đang lỗi hoặc đang tắt.
- **Graceful Shutdown (`SIGTERM`):** Khi nhận `SIGTERM`, server ngừng nhận request mới, xử lý nốt các request đang chạy dở, đóng kết nối rồi mới thoát với exit code `0`.
- **Tại sao state trong RAM bị hỏng khi scale nhiều instance?** Mỗi container/instance có bộ nhớ RAM riêng biệt. Nếu lưu lịch sử chat vào dict trong RAM, Request 1 vào `agent-1` lưu vào RAM của `agent-1`, nhưng Request 2 được Nginx chuyển sang `agent-2` sẽ không thấy lịch sử cũ. Chuyển sang **Stateless** (lưu chung vào Redis) giúp mọi instance đều đọc/ghi cùng một nguồn dữ liệu.

### Exercise 5.4 & 5.5: Load Balancing (Nginx + 3 instances) & `test_stateless.py`

- Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` (mở cổng `8080`, endpoint `POST /chat`) rồi chạy `python test_stateless.py`:
  - `Session ID`: `e48565b6-7ace-4642-8c8f-5d61b4a7bd31`
  - 5 request liên tiếp được Nginx phân tán đều qua cả 3 instance: `instance-fb1b17`, `instance-5dc1d0`, `instance-e78469` (Request 1→`fb1b17`, 2→`5dc1d0`, 3→`e78469`, 4→`fb1b17`, 5→`5dc1d0`).
  - Khi gọi `GET /chat/{session_id}/history`, hệ thống trả về đầy đủ **10 messages** (5 câu hỏi + 5 câu trả lời), chứng minh dù traffic nhảy qua lại giữa 3 instance khác nhau nhưng lịch sử hội thoại vẫn toàn vẹn nhờ lưu trong Redis.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` (chế độ đầy đủ có Docker trong WSL2):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log
- Dùng AI hỗ trợ giải thích đề bài Day 14, thiết lập môi trường WSL2/`.venv`, giải thích cơ chế `mock_llm.py`, `curl`, graceful shutdown (`SIGTERM` vs `SIGINT`), chạy và phân tích kết quả Part 1, Part 2, Part 4, Part 5, và hỗ trợ hoàn thiện các file TODO trong `06-lab-complete/` (Part 6). Đã tự kiểm tra toàn bộ bằng `python check_production_ready.py` đạt `PASS 12/12 (43/43 checks passed)`.
