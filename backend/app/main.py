"""FastAPI 入口。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import comm as comm_api
from app.api import scene as scene_api
from app.common.exceptions import register_exception_handlers
from app.services.engine import set_main_loop
from app.services.approval import _set_main_loop


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期：注册主 event loop 供后台 tick + 跨线程 ws 推送。"""
    loop = asyncio.get_running_loop()
    set_main_loop(loop)
    _set_main_loop(loop)
    yield


app = FastAPI(title="通信任务保障后端", version="0.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
register_exception_handlers(app)

# 路由
app.include_router(comm_api.router)
app.include_router(scene_api.router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}
