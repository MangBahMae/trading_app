"""신호 스캐너 대시보드 API 라우터."""
from fastapi import APIRouter, Query

from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as svc
from app.services import weekly as weekly_svc

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(refresh: bool = Query(False)) -> DashboardResponse:
    data = svc.get_dashboard_data(force_refresh=refresh)
    return DashboardResponse(**data)


@router.get("/dashboard/weekly", response_model=DashboardResponse)
def get_weekly_dashboard(refresh: bool = Query(False)) -> DashboardResponse:
    """주봉(1W) 차트와 주봉 신호. 선/존은 일봉에서 그린 것을 표시용으로만 내려준다."""
    return DashboardResponse(**weekly_svc.get_weekly_dashboard_data(force_refresh=refresh))
