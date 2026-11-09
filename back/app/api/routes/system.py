from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def read_root():
    return {
        "message": "智能学习计划管理系统后端运行成功！",
        "version": "0.1.0",
    }


@router.get("/health")
def health_check():
    return {"status": "ok"}