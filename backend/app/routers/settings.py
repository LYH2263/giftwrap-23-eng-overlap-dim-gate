from fastapi import APIRouter
from app.repositories import settings_repo
from app.schemas.settings import OverlapUpdate

router = APIRouter()


@router.get("/settings")
def settings():
    return settings_repo.get_all()


@router.put("/settings/overlap")
def set_overlap(body: OverlapUpdate):
    value = settings_repo.set_overlap(body.overlap)
    return {"key": "overlap", "value": str(value)}
