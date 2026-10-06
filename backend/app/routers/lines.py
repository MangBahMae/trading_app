"""수동 지지선/저항선/추세선 CRUD API 라우터.

lines_store.py 함수를 그대로 호출한다(app/services/dashboard.py 경유 -
그 모듈 docstring 참고, sys.path 삽입/bare import 창구를 하나로 유지하기 위함).
SQLite manual_lines.db 파일 위치/스키마는 원본과 완전히 동일(공유).
"""
from fastapi import APIRouter, HTTPException

from app.schemas.dashboard import HorizontalLineRequest, LineIdResponse, TrendLineRequest, ZoneRequest
from app.services import dashboard as svc

router = APIRouter(prefix="/api/lines", tags=["lines"])


@router.post("/horizontal", response_model=LineIdResponse)
def add_horizontal_line(payload: HorizontalLineRequest) -> LineIdResponse:
    line_id = svc.add_horizontal_line(payload.price)
    return LineIdResponse(id=line_id)


@router.post("/trend", response_model=LineIdResponse)
def add_trend_line(payload: TrendLineRequest) -> LineIdResponse:
    line_id = svc.add_trend_line(payload.time1, payload.price1, payload.time2, payload.price2)
    return LineIdResponse(id=line_id)


@router.put("/trend/{line_id}", response_model=LineIdResponse)
def update_trend(line_id: int, payload: TrendLineRequest) -> LineIdResponse:
    """추세선 두 점 수정 - 검증은 POST /trend와 같다. 대상이 추세선이 아니거나 없으면 404."""
    if not svc.update_trend(line_id, payload.time1, payload.price1, payload.time2, payload.price2):
        raise HTTPException(status_code=404, detail="추세선을 찾을 수 없음")
    return LineIdResponse(id=line_id)


@router.post("/zone", response_model=LineIdResponse)
def add_zone(payload: ZoneRequest) -> LineIdResponse:
    line_id = svc.add_zone(payload.time1, payload.price1, payload.time2, payload.price2)
    return LineIdResponse(id=line_id)


@router.put("/zone/{line_id}", response_model=LineIdResponse)
def update_zone(line_id: int, payload: ZoneRequest) -> LineIdResponse:
    """존 모양 수정 - 검증은 POST /zone과 같다. 대상이 존이 아니거나 없으면 404."""
    if not svc.update_zone(line_id, payload.time1, payload.price1, payload.time2, payload.price2):
        raise HTTPException(status_code=404, detail="존을 찾을 수 없음")
    return LineIdResponse(id=line_id)


@router.delete("/{line_id}")
def delete_line(line_id: int) -> dict:
    svc.delete_line(line_id)
    return {"ok": True}
