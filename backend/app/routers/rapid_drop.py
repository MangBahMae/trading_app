"""기존 독립 신호와 분리된 급락 대응 실험 API."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.services import rapid_drop_signals

router = APIRouter(prefix='/api', tags=['rapid-drop-experiment'])


@router.get('/rapid-drop')
def get_rapid_drop(day: date = Query(..., alias='date')) -> dict:
    try:
        return rapid_drop_signals.response_for_date(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
