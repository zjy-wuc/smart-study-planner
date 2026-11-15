
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.services import plan_lifecycle_service


router = APIRouter(
    prefix="/plans",
    tags=["Plan Lifecycle"],
)


@router.post("/{plan_id}/end")
def end_plan_early(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = plan_lifecycle_service.end_plan_early(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(
        data=result,
        message="计划已结束",
    )
