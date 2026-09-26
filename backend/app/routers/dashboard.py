"""신호 스캐너 대시보드 API 라우터."""
from fastapi import APIRouter, Query

from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as svc

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(refresh: bool = Query(False)) -> DashboardResponse:
    data = svc.get_dashboard_data(force_refresh=refresh)
    return DashboardResponse(**data)
