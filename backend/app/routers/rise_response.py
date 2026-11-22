"""BTCUSDT 마감 일봉의 상승 대응 실험."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.services import rise_response

router = APIRouter(prefix='/api', tags=['rise-response-experiment'])


@router.get('/rise-response')
def get_rise_response(day: date = Query(..., alias='date')) -> dict:
    try:
        return rise_response.response_for_date(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
