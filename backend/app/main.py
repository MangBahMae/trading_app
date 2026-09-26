"""FastAPI 앱 진입점.

Streamlit -> React 마이그레이션. 1단계(포지션 사이징 계산기)에 이어 2단계에서
신호 스캐너(차트+신호 패널) API를 추가했다 - scripts/pipeline.py 및 그 의존
모듈들을 app/services/에 그대로 이식(계산 로직 무변경, 회귀 테스트로 검증
완료 - backend/tests/test_regression_pipeline.py).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import dashboard, lines, position_sizing

app = FastAPI(title="trading_app API", version="0.1.0")

# 로컬 개발 중 Vite 기본 포트(5173)에서의 호출을 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(position_sizing.router)
app.include_router(dashboard.router)
app.include_router(lines.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
