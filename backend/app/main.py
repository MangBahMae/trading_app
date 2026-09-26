"""FastAPI 앱 진입점.

Streamlit -> React 마이그레이션 1단계: 기존 scripts/*.py 계산 로직을 API로
감싸는 백엔드. 이번 단계는 포지션 사이징 계산기만 다룬다(신호 스캐너는
scripts/pipeline.py 등 df 기반 로직이 커서 다음 단계에서 별도로 옮긴다).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import position_sizing

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
