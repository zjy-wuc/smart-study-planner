from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success(data=None, message="success", code=200):
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "data": jsonable_encoder(data)#转换成json格式
        }
    )


def error(code=400, message="Request failed", data=None):
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "data": jsonable_encoder(data)
        }
    )