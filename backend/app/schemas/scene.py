"""引擎接口 schema：state / start / pause / reset / decide / input / ws。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- 引擎状态 ----------
class SceneStateOut(BaseModel):
    """场景引擎当前状态。"""

    now_min: int
    is_paused: bool
    is_running: bool
    pending_events: int = 0
    pending_approvals: int = 0


class SceneStartIn(BaseModel):
    """场景启动入参。"""

    offset_min: int = Field(default=0, ge=0, description="模拟初始已流逝分钟数")


# ---------- 决策 ----------
class SceneDecideIn(BaseModel):
    """引擎级决策入参（与审批合并）。

    优先使用 plan_code（直接对方案决策）。如传 approval_code 则按旧路径兼容。
    decision_source / approver 透传给 service 层，默认"人工"。
    """

    plan_code: Optional[str] = None
    approval_code: Optional[str] = None
    decision: str = Field(description="批准 / 拒绝")
    reason: Optional[str] = None
    approver: str = Field(default="ROLE-APPROVER")
    decision_source: str = Field(default="人工")


# ---------- 事件流 ----------
class WsMessage(BaseModel):
    """WebSocket 消息体。"""

    type: str
    payload: Optional[Any] = None
    ts: Optional[float] = None
