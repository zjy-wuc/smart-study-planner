from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def read_root():
    return {
        "message": "学迹后端运行成功！",
        "version": "0.1.0",
    }


@router.get("/health")
def health_check():
    return {"status": "ok"}
