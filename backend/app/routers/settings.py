from fastapi import APIRouter
from app.repositories import settings_repo
from app.schemas.settings import SettingsUpdate
router = APIRouter()
@router.get("/settings")
def settings(): return settings_repo.get_all()
@router.put("/settings")
def update_settings(body: SettingsUpdate):
    settings_repo.set_overlap(body.overlap)
    # 读回持久化结果，而不是回显请求体
    return settings_repo.get_all()
