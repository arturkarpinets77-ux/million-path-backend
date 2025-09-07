from fastapi import APIRouter, Depends
from app.models import Settings
from app.utils.storage import load_settings, save_settings
from app.utils.auth import require_bearer

router = APIRouter()

@router.get("/settings", response_model=Settings)
def get_settings():
    return load_settings()

@router.put("/settings", response_model=Settings)
def update_settings(body: Settings, _: bool = Depends(require_bearer)):
    save_settings(body)
    return body
