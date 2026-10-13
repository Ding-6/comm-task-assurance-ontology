"""场景引擎路由：state / start / pause / reset / decide / input / ws。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.database import get_db as _get_db
from app.schemas.scene import SceneDecideIn, SceneStartIn
from app.schemas.comm import ApiResponse
from app.services.approval import decide_approval
from app.services.engine import (
    handle_input as engine_handle_input,
    get_state as engine_get_state,
    pause_scene,
    reset_scene,
    resume_scene,
    start_scene,
)
from app.models.approval import ApprovalRecord

router = APIRouter(prefix="/scene", tags=["scene"])


@router.get("/state", response_model=ApiResponse)
def state(db: Session = Depends(_get_db)) -> ApiResponse:
    return ApiResponse(data=engine_get_state(db))


@router.post("/start", response_model=ApiResponse)
def start(payload: SceneStartIn) -> ApiResponse:
    # V4.1 不支持 offset，直接以真实墙钟为锚点
    _ = payload  # 保留 schema 兼容
    return ApiResponse(data=start_scene())


@router.post("/pause", response_model=ApiResponse)
def pause() -> ApiResponse:
    return ApiResponse(data=pause_scene())


@router.post("/resume", response_model=ApiResponse)
def resume() -> ApiResponse:
    return ApiResponse(data=resume_scene())


@router.post("/reset", response_model=ApiResponse)
def reset() -> ApiResponse:
    return ApiResponse(data=reset_scene())


@router.post("/decide", response_model=ApiResponse)
def decide(payload: SceneDecideIn, db: Session = Depends(_get_db)) -> ApiResponse:
    # 优先 plan_code（SK-04 规范）；兼容旧 approval_code
    target = payload.plan_code or payload.approval_code
    if not target:
        return ApiResponse(code=400, message="plan_code / approval_code 必填")
    if payload.approval_code and not payload.plan_code:
        # 老路径：先查 ApprovalRecord；查不到时按 create_or_get_approval 的占位编码 APV-{plan} 剥前缀
        ap: ApprovalRecord | None = db.get(ApprovalRecord, target)
        if ap is not None and ap.plan_code:
            target = ap.plan_code
        elif target.startswith("APV-"):
            target = target[len("APV-"):]
    decided = decide_approval(
        db,
        approval_code=target,
        decision=payload.decision,
        approver=payload.approver,
        decision_source=payload.decision_source,
        reason=payload.reason,
    )
    db.commit()
    return ApiResponse(data={"approval_code": decided.approval_code, "decision": decided.decision})


@router.post("/input")
def input_route(payload: dict[str, Any], db: Session = Depends(_get_db)) -> ApiResponse:
    """引擎层 input：category + payload。"""
    category: str = payload.get("category", "")
    body: Any = payload.get("payload", "")
    try:
        result = engine_handle_input(db, category, body)
        db.commit()
        return ApiResponse(data=result)
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))


@router.websocket("/ws")
async def scene_ws(ws: WebSocket) -> None:
    hub = get_hub()
    await hub.connect(ws)
    # 新连接先推一次完整 state
    from app.core.database import SessionLocal

    s = SessionLocal()
    try:
        snap = engine_get_state(s)
    finally:
        s.close()
    try:
        await ws.send_json({"type": "state", "data": snap})
    except Exception:
        pass

    try:
        while True:
            # 保持连接，不强制读消息
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
