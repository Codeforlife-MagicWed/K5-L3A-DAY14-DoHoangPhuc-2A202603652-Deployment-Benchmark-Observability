"""
Production AI Agent — Part 6 Final Project
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mỗi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
        }
        msg = record.getMessage()
        if msg.startswith("{"):
            try:
                parsed = json.loads(msg)
                if isinstance(parsed, dict):
                    payload.update(parsed)
                    return json.dumps(payload, ensure_ascii=False)
            except ValueError:
                pass
        payload["msg"] = msg
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("agent")
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    return app_logger


logger = _configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý startup và graceful shutdown khi nhận SIGTERM."""
    logger.info(json.dumps({"event": "startup", "env": settings.environment, "port": settings.port}))
    yield
    logger.info(json.dumps({"event": "shutdown", "env": settings.environment}))
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn chạy."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi Redis kết nối được, 503 khi mất kết nối."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Endpoint chính: Auth -> Rate Limit -> Cost Guard -> LLM -> Record Cost."""
    start = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "event": "ask",
                "path": "/ask",
                "status": 200,
                "ms": elapsed_ms,
                "cost_usd": round(cost_usd, 6),
            }
        )
    )
    return {
        "question": body.question,
        "answer": answer,
        "environment": settings.environment,
    }
