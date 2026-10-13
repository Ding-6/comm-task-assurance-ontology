"""自定义异常与全局异常处理器。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.comm import ApiResponse


class BizException(Exception):
    """业务异常。"""

    def __init__(
        self,
        message: str,
        code: int = 1,
        data: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.code = code
        self.data = data
        super().__init__(message)


def _payload(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return ApiResponse(code=code, message=message, data=data).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理。"""

    @app.exception_handler(BizException)
    async def biz_handler(_: Request, exc: BizException) -> JSONResponse:
        return JSONResponse(status_code=200, content=_payload(exc.code, exc.message, exc.data))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=_payload(400, "参数校验失败", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=200, content=_payload(500, f"服务器异常: {exc}"))
