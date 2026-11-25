# Deployment Information

## Public URL
https://agent-production-9bf6a6c9.up.railway.app

## Platform
Railway (`06-lab-complete/` — Dockerfile + Railway Redis)

## Test Commands

### 1. Health Check (Liveness)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-9bf6a6c9.up.railway.app/health"
# Expected: 200
# Body: {"status":"ok","environment":"production"}
```

### 2. Readiness Check (Redis connection)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-9bf6a6c9.up.railway.app/ready"
# Expected: 200
# Body: {"status":"ready"}
```

### 3. API Test (no API key → 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-production-9bf6a6c9.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401
```

### 4. API Test (with authentication → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-production-9bf6a6c9.up.railway.app/ask" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 200
```

## Environment Variables Set (on Railway Dashboard)
- `PORT` (tự động cấp bởi Railway)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — trỏ tới Railway Redis service)
- `AGENT_API_KEY` (đặt trên Railway, không ghi vào Git)
- `ENVIRONMENT` (`production`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
