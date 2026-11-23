"""BTCUSDT 일봉 돌파·재시험 실험 API."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.services import breakout_signals

router = APIRouter(prefix='/api', tags=['breakout-retest-experiment'])


@router.get('/breakout-retest')
def get_breakout_retest(day: date = Query(..., alias='date')) -> dict:
    try:
        return breakout_signals.response_for_date(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
