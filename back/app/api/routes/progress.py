
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.services import progress_service


router = APIRouter(
    prefix="/plans",
    tags=["Plan Progress"],
)


@router.get("/{plan_id}/progress")
def get_plan_progress(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = progress_service.get_plan_progress(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(
        data=result,
        message="计划进度查询成功",
    )
