# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Đỗ Hoàng Phúc (2A202603652)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows + WSL2 (Ubuntu, Python 3.12) & Docker Desktop

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi trong dưới nửa giây (mock base latency ~120–180ms + retrieval ~20ms; ngưỡng 500ms chịu được dao động nhẹ nhưng bắt được khi hệ thống quá tải hoặc tail latency tăng cao) |
| Error rate `/ask` | < 2 % | Cho phép sai số nhỏ từ lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01` mặc định ~1%) mà không gây báo động giả |
| Accuracy trên golden dataset | ≥ 85 % | Đảm bảo agent trả lời đúng đa số câu hỏi chuyên môn trước khi cho phép merge/deploy lên production |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.18 | 191.4 | 220.5 | 1709.9 | 1.33% | PASS |
| 10 | 35.30 | 192.5 | 223.0 | 1708.3 | 0.67% | PASS |
| 50 | 113.37 | 197.4 | 336.4 | 1690.5 | 1.00% | PASS |
| 100 | 64.62 | 415.0 | 2738.5 | 3051.1 | 1.67% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính mãi. Từ concurrency `1 → 10 → 50`, RPS tăng mạnh (`4.18 → 35.30 → 113.37 req/s`) nhờ xử lý bất đồng bộ (`async/await`). Nhưng lên tới `100`, hệ thống chạm điểm bão hòa (event loop / CPU của 1 worker + hàng đợi kết nối), nên RPS tụt xuống còn `64.62 req/s` trong khi `p50` tăng hơn gấp đôi (`415.0 ms`) và `p95` nhảy vọt lên `2738.5 ms` (vi phạm SLO ≤ 500 ms).

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 192.2 | 222.8 | 241.8 |
| 0.03 (mặc định) | 227.1 | 222.2 | 1710.1 |
| 0.1 | 311.1 | 1686.6 | 1710.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và sau đó là `p95` khi tỉ lệ chậm lên 10%) nhạy nhất với các request chậm bất thường: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03`, `avg` chỉ nhích nhẹ từ `192.2 ms` lên `227.1 ms` (+35 ms), nhưng `p99` nhảy vọt hơn 7 lần từ `241.8 ms` lên `1710.1 ms`. Khi `MOCK_SLOW_RATE=0.1`, `avg = 311.1 ms` vẫn trông "ổn", nhưng `p95 = 1686.6 ms` đã vượt xa SLO 500ms. Vì vậy, SLO phải đặt theo **p95/p99** để bảo vệ trải nghiệm thực tế của nhóm người dùng gặp độ trễ đuôi (tail latency), tránh bị giá trị trung bình che giấu.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000394 | $0.000759 | $0.000790 |
| Cost / câu đúng (USD) | $0.00039375 | $0.00003616 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu về JWT (`["jwt"]`) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm tài liệu về Kubernetes HPA (`["hpa", "kubernetes", "autoscal"]`) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent v2 thêm bước retrieval (RAG) nên prompt dài hơn (avg tokens tăng từ `56.3` lên `113.7` tokens/câu) và tổng chi phí tăng gần gấp đôi (`$0.000394 → $0.000790`), đồng thời thêm ~20ms latency cho bước tìm tài liệu. Tuy nhiên, độ chính xác nhảy vọt từ `4.3%` lên `100.0%`, khiến chỉ số **cost / câu đúng** của v2 (`$0.00003436`) rẻ hơn hơn **11 lần** so với v1 (`$0.00039375`). Để chặn regression tự động khi merge code, file `.github/workflows/eval.yml` chạy `run_eval.py --min-accuracy 0.85`: nếu accuracy tụt dưới ngưỡng hoặc có câu regression so với baseline, script trả về **exit code `1`** làm job CI fail và chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Quan sát Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

**Trả lời câu hỏi Exercise 7.4:**
1. **p95 và avg:** Khi đang chịu tải 30 user (Locust), đo từ Prometheus: `avg ≈ 204 ms` (`0.204s`), `p95 ≈ 291 ms` (`0.291s`). Khoảng cách giữa `avg` và `p95` (~87 ms) phản ánh sự tồn tại của các request chậm ở phần đuôi (`MOCK_SLOW_RATE`) kéo p95 lên cao hơn trung bình.
2. **Nginx chia tải:** Khi scale 2–3 instance và theo dõi header `X-Served-By` / panel *Requests/s theo instance*, Nginx phân tán traffic đều giữa các instance healthy theo round-robin và tự loại bỏ instance bị pause/down khỏi vòng quay.
3. **Vì sao input tokens/s > output tokens/s?** Thực tế đo được `input ≈ 1040.6 tok/s`, `output ≈ 545.0 tok/s` (~gấp đôi). Nguyên nhân là agent `v2` (RAG) ghép thêm `SYSTEM_PROMPT`, tài liệu truy xuất từ `KNOWLEDGE_BASE` và câu hỏi người dùng vào prompt đầu vào, nên input luôn dài hơn câu trả lời đầu ra.
4. **`curl http://localhost:8080/metrics` trả về gì?** Trả về **`404 Not Found`** (từ Nginx). Vì trong `nginx/nginx.conf`, Nginx chặn public route `/metrics` để không lộ số liệu nội bộ và chỉ cho phép Prometheus truy cập nội bộ trong Docker network `obs_net`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~65 giây (`for: 1m`) | Golden Signals — Error rate / LLM calls ok vs error |
| B | `MOCK_SLOW_RATE=0.3` | *(Không chạy trực tiếp; dự kiến `AgentHighLatencyP95` sau `for: 2m`)* | — | Latency & Traffic (p95/p99) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` *(cũng kích hoạt khi RPS/cost 5m vượt $2/h)* | ~120 giây (`for: 2m`) | Cost USD/giờ & LLM Latency |
| D | `docker pause` 1 instance (`agent-1`) | `AgentInstanceDown` | ~38 giây (`for: 30s`) | Golden Signals — Instances Up (`2 → 1`) & Req/s theo instance |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | Retrieval hit ratio tụt về 0, bảng version đổi `v2 → v1`, tokens/s giảm |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Các alert hạ tầng (Prometheus) chỉ đo được latency, HTTP 5xx, CPU/RAM và chi phí — chúng không biết câu trả lời có *đúng* hay không. Để phát hiện lỗi chất lượng khi model/version bị tụt cấp (`v2 → v1`), cần:
1. Chạy **Eval tự động trên golden dataset (`run_eval.py`) trong CI/CD** trước khi deploy (quality gate).
2. Giám sát các **metric đặc thù của RAG/AI** như *Retrieval hit ratio* (tụt về 0%), độ dài output, và thu thập **user feedback** (thumbs up/down) + chạy **online eval / LLM-as-judge** lấy mẫu trên traffic production.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong log & Jaeger:

- `trace_id`: `23087047c38837a7a005e53f6c90a631`
- Tổng thời gian: `1719.3 ms` (`http_request.ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1694.8 ms`, chiếm **98.6%** tổng thời gian request)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T13:40:03.198688+00:00", "level": "INFO", "service": "observable-agent", "instance": "9bb59616098c", "event": "llm_call", "trace_id": "23087047c38837a7a005e53f6c90a631", "span_id": "5e2dba90ccdc57e9", "request_id": "e5b386c367c3", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 76, "output_tokens": 39, "cost_usd": 3.5e-05, "llm_ms": 1694.8}
```

- Trace lỗi mẫu (`error=true` trong Jaeger, `trace_id`: `0c2c9ecc88b5f00c0bd7ec83725dc7a8`):

```json
{"ts": "2026-11-25T13:40:02.564282+00:00", "level": "INFO", "service": "observable-agent", "instance": "9bb59616098c", "event": "llm_error", "trace_id": "0c2c9ecc88b5f00c0bd7ec83725dc7a8", "span_id": "018950e8637ad6e5", "request_id": "cac9c3a307a7", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu `Aggregated` lấy từ `scale_1_stats.csv` và `scale_3_stats.csv` (trong đó lượt 2 có `deploy.replicas: 2` khi chạy `locust`):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58.94 | 210 | 1100 | 1800 | 58 (0.80%) |
| 3 (stack scaled) | 61.20 | 200 | 470 | 1700 | 71 (0.93%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Có cải thiện rõ rệt ở **p95** (giảm hơn một nửa từ `1100 ms` xuống `470 ms`, đưa hệ thống trở lại đạt SLO `< 500 ms`!) vì khi tăng số instance, lượng request xếp hàng chờ CPU/worker ở mỗi container giảm mạnh (`POST /ask` p95 giảm từ `1200 ms` xuống `510 ms`). Tuy nhiên **p99 (`1700–1800 ms`) gần như không đổi** và **RPS tăng ít** (`58.94 → 61.20`) vì:
1. Nút thắt của `p99` nằm ở **độ trễ của chính LLM upstream** (`MOCK_SLOW_RATE` tạo các call ~1.5–1.7s, scale thêm instance không làm model LLM trả lời nhanh hơn).
2. Ngoài ra trong kịch bản Locust, mỗi user ảo có `wait_time` nghỉ giữa các request nên 100 users tạo ra tốc độ gửi tải giới hạn (~60 req/s).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Latency trung bình che giấu tail latency:** phải đặt SLO và theo dõi theo `p95`/`p99` thay vì `average`.
  2. **Eval chất lượng bổ sung cho Observability hạ tầng:** metrics/alerts chỉ phát hiện lỗi 5xx/chậm/hết tiền, còn chất lượng trả lời giảm (`v2 → v1`) chỉ bắt được bằng golden dataset & quality gate trong CI.
  3. **3 trụ cột liên kết chặt chẽ:** nhìn **Metrics** (Grafana/Prometheus) thấy spike → sang **Traces** (Jaeger) khoanh vùng đúng span chậm (`chat mock-llm-small` chiếm 98.6%) → lấy `trace_id` tra **JSON Logs** để thấy chi tiết lỗi/token.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Thêm metric & alert cho **Retrieval hit ratio tụt thấp** (phát hiện lỗi RAG/Vector DB rỗng), **tỉ lệ 401/429 bất thường** (phát hiện tấn công brute-force/spam), và **Redis latency / memory usage** (vì rate limiter & cost guard phụ thuộc Redis).
