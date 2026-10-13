"""业务接口 schema：SK-01~SK-10 + 查询。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- 通用响应 ----------
class ApiResponse(BaseModel):
    """统一响应外壳。"""

    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None


# ---------- 链路 ----------
class LinkOut(BaseModel):
    """链路视图。"""

    link_code: str
    link_name: str
    capacity_gbps: float
    warning_gbps: float
    oper_state: str
    avg_repair_min: Optional[int] = None
    lookahead_min: Optional[int] = None
    backup_link_code: Optional[str] = None
    current_load_gbps: Optional[float] = None
    future_load_gbps: Optional[float] = None
    warn_status: Optional[str] = None


# ---------- 任务 ----------
class TaskOut(BaseModel):
    """任务视图。"""

    task_code: str
    task_name: str
    duration_min: int
    critical_min: Optional[int] = None
    owner_role: Optional[str] = None
    current_link_code: Optional[str] = None
    initial_demand_gbps: float
    lookahead_min: Optional[int] = None


# ---------- 告警 ----------
class AlarmInjectIn(BaseModel):
    """SK-01 注入告警入参。"""

    link_code: str
    alarm_type: str = Field(description="link_down / 性能劣化 / 容量超限")
    native_severity: str = Field(description="critical / major / minor / warning")
    predicted_min: Optional[int] = None


class AlarmOut(BaseModel):
    """告警视图。"""

    alarm_code: str
    link_code: str
    alarm_type: str
    native_severity: str
    event_min: int
    predicted_min: Optional[int] = None


# ---------- 方案 ----------
class PlanOut(BaseModel):
    """方案视图。"""

    plan_code: str
    alarm_code: str
    plan_type: str
    link_code: str
    target_link_code: Optional[str] = None
    est_repair_min: Optional[int] = None
    predicted_load_after_gbps: Optional[float] = None
    can_meet_critical: Optional[str] = None
    status: Optional[str] = None
    is_default: Optional[str] = None
    recommendation: Optional[str] = None
    generated_min: Optional[int] = None


# ---------- 审批 ----------
class ApprovalIn(BaseModel):
    """SK-04 人工决策入参（对齐说明书 §4.04）。"""

    plan_code: str
    decision: str = Field(description="批准 / 拒绝")
    reason: Optional[str] = None
    approver: str = Field(
        default="ROLE-APPROVER",
        description="审批人；超时自动分支由系统以 SYSTEM 身份执行",
    )
    decision_source: str = Field(
        default="人工",
        description="决定来源：人工 / 超时自动",
    )


class ApprovalOut(BaseModel):
    """审批视图。"""

    approval_code: str
    plan_code: Optional[str] = None
    decision: Optional[str] = None
    reason: Optional[str] = None
    approver: Optional[str] = None
    decision_source: Optional[str] = None
    decided_min: Optional[int] = None


# ---------- 修理 ----------
class RepairRequestIn(BaseModel):
    """SK-05 修理申请入参。"""

    alarm_code: str
    plan_code: Optional[str] = None


class RepairReceiveIn(BaseModel):
    """SK-06 修理回执/完成入参（对齐说明书 §4.05）。

    est_finish_min / actual_finish_min：相对当前场景分钟数的"预计/实际时长"（分钟）。
    接口层会转换为绝对场景分钟再写入 comm_repair_order。
    至少需要传一个：只传 est_finish_min = 回执；只传 actual_finish_min = 完成。
    """

    order_code: str
    est_finish_min: Optional[int] = None
    actual_finish_min: Optional[int] = None
    as_of_min: Optional[int] = None


class RepairOrderOut(BaseModel):
    """修理单视图。"""

    order_code: str
    link_code: str
    alarm_code: Optional[str] = None
    request_min: int
    est_finish_min: Optional[int] = None
    actual_finish_min: Optional[int] = None
    status: Optional[str] = None


# ---------- 输入 ----------
class InputIn(BaseModel):
    """SK-10 自然语言输入框入参。"""

    text: str


# ---------- 切换（SK-01） ----------
class SwitchIn(BaseModel):
    """SK-01 链路故障切换入参。"""

    alarm_link_code: str = Field(min_length=1, description="发生异常告警的链路编码")
    moved_task_code: Optional[str] = Field(
        default=None, description="留空则自动识别该链路全部任务"
    )
    as_of_min: Optional[int] = Field(default=None, ge=0)


# ---------- 方案生成（SK-03） ----------
class PlanGenerateIn(BaseModel):
    """SK-03 方案生成入参。"""

    alarm_link_code: str = Field(min_length=1, description="待处置的异常链路编码")
    as_of_min: Optional[int] = Field(default=None, ge=0)


# ---------- 链路恢复（SK-07） ----------
class RestoreIn(BaseModel):
    """SK-07 链路恢复与任务回迁入参。"""

    link_code: str = Field(min_length=1, description="已修复恢复 up 的链路编码")
    as_of_min: Optional[int] = Field(default=None, ge=0)


# ---------- 添加任务（SK-08） ----------
class TaskAddIn(BaseModel):
    """SK-08 添加任务入参。"""

    task_code: str = Field(min_length=1, description="任务编码 T-A/T-B/T-C/...")
    task_name: str = Field(min_length=1, description="任务名称")
    duration_min: int = Field(ge=1, description="任务持续时间（分钟）")
    critical_min: Optional[int] = Field(default=None, ge=0, description="关键阶段相对分钟")
    link_code: str = Field(min_length=1, description="初始承载链路")
    demand_gbps: float = Field(ge=0, description="初始需求带宽 Gbps")
    owner_role: Optional[str] = Field(default=None, description="责任角色；缺省 ROLE-DUTY")
    lookahead_min: Optional[int] = Field(default=30, ge=0)


# ---------- 添加链路（SK-09） ----------
class LinkAddIn(BaseModel):
    """SK-09 添加链路入参。"""

    link_code: str = Field(min_length=1, description="链路编码")
    link_name: str = Field(min_length=1, description="链路名称")
    capacity_gbps: float = Field(gt=0, description="容量 Gbps")
    warning_gbps: float = Field(gt=0, description="预警线 Gbps")
    oper_state: str = Field(default="up", description="up / down")
    avg_repair_min: Optional[int] = Field(default=30, ge=0)
    lookahead_min: Optional[int] = Field(default=30, ge=0)
    backup_link_code: Optional[str] = Field(default=None)


# ---------- 需求变更（SK-10） ----------
class DemandIn(BaseModel):
    """SK-10 需求变更入参。"""

    task_code: str = Field(min_length=1)
    valid_from_min: Optional[int] = Field(
        default=None, ge=0, description="生效时刻（相对分钟）；缺省=now_min()"
    )
    demand_gbps: float = Field(gt=0, description="需求带宽 Gbps")


# ---------- 前瞻 / 预检 ----------
class ForecastQuery(BaseModel):
    """GET /comm/forecast query 入参。"""

    link_code: str = Field(min_length=1, description="链路编码，必填且非空")
    as_of_min: Optional[int] = Field(default=None, ge=0, description="模拟当前场景分钟；缺省=now_min()")


class PrecheckIn(BaseModel):
    """POST /comm/precheck/task body 入参。"""

    link_code: str = Field(min_length=1)
    demand_gbps: float = Field(ge=0, description="模拟新增需求带宽（Gbps）")
    as_of_min: Optional[int] = Field(default=None, ge=0)
