
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "message": "智能学习计划管理系统后端运行成功！",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
