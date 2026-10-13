"""SK-01~SK-10 业务路由 + 查询接口。

路径严格对齐《本体规格说明书 V4.1》§7.1 / §7.2：

业务接口：
  POST /api/comm/alarm          注入告警
  POST /api/comm/switch         链路故障切换
  POST /api/comm/occupancy      计算链路占用与前瞻
  POST /api/comm/plan           生成处置方案
  POST /api/comm/approve        人工审批决策
  POST /api/comm/repair         修理回执 / 修理完成
  POST /api/comm/restore        链路恢复与任务回迁
  POST /api/comm/task           添加任务
  POST /api/comm/link           添加链路
  POST /api/comm/demand         需求变更登记

查询接口：
  GET  /api/comm/snapshot       场景快照
  GET  /api/comm/links          链路列表（别名，保留）
  GET  /api/comm/tasks          任务列表（别名，保留）
  GET  /api/comm/alarms         告警列表
  GET  /api/comm/plans          方案列表
  GET  /api/comm/approvals      审批记录
  GET  /api/comm/repairs        修理单列表
  GET  /api/comm/events         事件流水
  POST /api/comm/reset          复位

扩展能力（说明书未列，保留现状）：
  GET  /api/comm/forecast       前瞻预测点采样
  POST /api/comm/precheck/task  添加任务容量预检
  GET  /api/comm/evidence/report  T+120 全窗口证据核对报告
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.database import get_db
from app.core.scene_clock import get_clock
from app.models.alarm import ResourceAlarm
from app.models.approval import ApprovalRecord
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.plan import CommPlan
from app.models.repair_order import RepairOrder
from app.models.task import CommTask
from app.schemas.comm import (
    AlarmInjectIn,
    AlarmOut,
    ApiResponse,
    ApprovalIn,
    ApprovalOut,
    DemandIn,
    ForecastQuery,
    LinkAddIn,
    LinkOut,
    PlanGenerateIn,
    PlanOut,
    PrecheckIn,
    RepairOrderOut,
    RepairReceiveIn,
    RestoreIn,
    SwitchIn,
    TaskAddIn,
    TaskOut,
)
from app.services.approval import decide_approval
from app.services.engine import _add_link, _add_task, _reset_default_scene
from app.services.evidence import get_evidence_report
from app.services.occupancy import calc_occupancy, recalc_all, update_link_loads
from app.services.plan import generate_plans
from app.services.precheck import precheck_task
from app.services.repair import handle_repair_update
from app.services.restore import handle_link_restored
from app.services.switch import handle_link_down

router = APIRouter(prefix="/comm", tags=["comm"])


# ============================================================
# 查询 / 列表
# ============================================================

@router.get("/links", response_model=ApiResponse)
def list_links(db: Session = Depends(get_db)) -> ApiResponse:
    """链路列表（实时重算占用）。"""
    update_link_loads(db)
    db.commit()
    rows: List[CommLink] = list(db.scalars(select(CommLink)))
    return ApiResponse(data=[LinkOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/tasks", response_model=ApiResponse)
def list_tasks(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[CommTask] = list(db.scalars(select(CommTask)))
    return ApiResponse(data=[TaskOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/alarms", response_model=ApiResponse)
def list_alarms(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[ResourceAlarm] = list(db.scalars(select(ResourceAlarm)))
    return ApiResponse(data=[AlarmOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/plans", response_model=ApiResponse)
def list_plans(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[CommPlan] = list(db.scalars(select(CommPlan)))
    return ApiResponse(data=[PlanOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/approvals", response_model=ApiResponse)
def list_approvals(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[ApprovalRecord] = list(db.scalars(select(ApprovalRecord)))
    return ApiResponse(data=[ApprovalOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/repairs", response_model=ApiResponse)
def list_repairs(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[RepairOrder] = list(db.scalars(select(RepairOrder)))
    return ApiResponse(data=[RepairOrderOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/events", response_model=ApiResponse)
def list_events(db: Session = Depends(get_db)) -> ApiResponse:
    rows: List[SceneEvent] = list(db.scalars(select(SceneEvent).order_by(SceneEvent.occur_min)))
    return ApiResponse(
        data=[
            {
                "event_code": r.event_code,
                "event_type": r.event_type,
                "ref_type": r.ref_type,
                "ref_code": r.ref_code,
                "occur_min": r.occur_min,
                "summary": r.summary,
            }
            for r in rows
        ]
    )


@router.get("/snapshot", response_model=ApiResponse)
def get_snapshot(db: Session = Depends(get_db)) -> ApiResponse:
    """场景快照（说明书 §7.2 GET /api/comm/snapshot）：

    聚合：链路 + 任务 + 待审批方案 + 最近事件 + 预订事件 + 当前分钟。
    """
    clock = get_clock()
    now_min: int = clock.now_min()
    update_link_loads(db)
    db.commit()

    links = list(db.scalars(select(CommLink)))
    tasks = list(db.scalars(select(CommTask)))
    plans = list(
        db.scalars(select(CommPlan).where(CommPlan.status == "待审批"))
    )
    events = list(
        db.scalars(select(SceneEvent).order_by(SceneEvent.occur_min.desc()).limit(20))
    )
    booked = list(
        db.scalars(
            select(SceneEvent)
            .where(
                SceneEvent.event_type == "task_booked",
                SceneEvent.occur_min > now_min,
            )
            .order_by(SceneEvent.occur_min.asc())
        )
    )

    return ApiResponse(
        data={
            "now_min": now_min,
            "is_paused": clock.is_paused,
            "is_running": clock.is_running(),
            "links": [LinkOut.model_validate(l, from_attributes=True).model_dump() for l in links],
            "tasks": [TaskOut.model_validate(t, from_attributes=True).model_dump() for t in tasks],
            "pending_approvals": [
                PlanOut.model_validate(p, from_attributes=True).model_dump() for p in plans
            ],
            "events": [
                {
                    "event_code": e.event_code,
                    "event_type": e.event_type,
                    "ref_type": e.ref_type,
                    "ref_code": e.ref_code,
                    "occur_min": e.occur_min,
                    "summary": e.summary,
                }
                for e in events
            ],
            "booked_events": [
                {"occur_min": b.occur_min, "summary": b.summary, "remain_min": b.occur_min - now_min}
                for b in booked
            ],
        }
    )


@router.post("/reset", response_model=ApiResponse)
def reset_scene(db: Session = Depends(get_db)) -> ApiResponse:
    """复位：清空业务表 + 重新加载默认三任务三链路 + 两条预订事件。"""
    _reset_default_scene(db)
    db.commit()
    return ApiResponse(message="ok")


# ============================================================
# 扩展能力（说明书未列但保留）
# ============================================================

@router.get("/forecast", response_model=ApiResponse)
def get_link_forecast(
    q: ForecastQuery = Depends(),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """前瞻预测：链路在 [now, now+lookahead] 内的阶梯式 predicted_load。"""
    from app.services.forecast import get_forecast

    try:
        data = get_forecast(db, q.link_code, as_of_min=q.as_of_min)
        return ApiResponse(data=data)
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))


@router.post("/precheck/task", response_model=ApiResponse)
def precheck_add_task(
    payload: PrecheckIn,
    db: Session = Depends(get_db),
) -> ApiResponse:
    """添加任务容量预检（不落库）。"""
    try:
        data = precheck_task(
            db,
            payload.link_code,
            payload.demand_gbps,
            as_of_min=payload.as_of_min,
        )
        return ApiResponse(data=data)
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))


@router.get("/evidence/report", response_model=ApiResponse)
def get_evidence(db: Session = Depends(get_db)) -> ApiResponse:
    """T+120 全窗口证据核对报告。"""
    return ApiResponse(data=get_evidence_report(db))


# ============================================================
# SK-01 注入告警 → POST /api/comm/alarm
# ============================================================

@router.post("/alarm", response_model=ApiResponse)
def inject_alarm(payload: AlarmInjectIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-01 注入告警。"""
    seq = len(list(db.scalars(select(ResourceAlarm)))) + 1
    code = f"AL-{seq:02d}"
    now = get_clock().now_min()
    alarm = ResourceAlarm(
        alarm_code=code,
        link_code=payload.link_code,
        alarm_type=payload.alarm_type,
        native_severity=payload.native_severity,
        event_min=now,
        predicted_min=payload.predicted_min,
    )
    db.add(alarm)
    db.add(
        SceneEvent(
            event_code=f"EVT-AI-{datetime.now().strftime('%H%M%S%f')}",
            event_type="alarm_injected",
            ref_type="alarm",
            ref_code=code,
            occur_min=now,
            summary=f"{code} {payload.alarm_type} @ {payload.link_code}",
        )
    )
    db.commit()
    return ApiResponse(data=AlarmOut.model_validate(alarm, from_attributes=True))


# ============================================================
# SK-02 故障切换 → POST /api/comm/switch
# ============================================================

@router.post("/switch", response_model=ApiResponse)
def switch_link(payload: SwitchIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-02 ACT-01 链路故障切换。"""
    result = handle_link_down(
        db,
        alarm_link_code=payload.alarm_link_code,
        as_of_min=payload.as_of_min,
    )
    db.commit()
    return ApiResponse(data=result)


# ============================================================
# SK-02 占用计算 → POST /api/comm/occupancy
# ============================================================

@router.post("/occupancy", response_model=ApiResponse)
def calc_occupancy_api(payload: dict, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-02 ACT-02 单条链路占用 + 前瞻扫描（链路编码由 body 传入）。"""
    link_code = (payload or {}).get("link_code")
    as_of_min = (payload or {}).get("as_of_min")
    if not link_code:
        return ApiResponse(code=400, message="link_code 必填")
    try:
        data = calc_occupancy(db, link_code=link_code, as_of_min=as_of_min)
        return ApiResponse(data=data)
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))


# ============================================================
# SK-03 方案生成 → POST /api/comm/plan
# ============================================================

@router.post("/plan", response_model=ApiResponse)
def gen_plans(payload: PlanGenerateIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-03 ACT-03 生成方案；返回 REPAIR + REROUTE（默认 REROUTE 标 is_default=是）。"""
    try:
        result = generate_plans(
            db,
            alarm_link_code=payload.alarm_link_code,
            as_of_min=payload.as_of_min,
        )
        db.commit()
        plans = result.get("plans", [])
        return ApiResponse(
            data={
                "plans": [PlanOut.model_validate(p, from_attributes=True).model_dump() for p in plans],
                "deadline_min": result.get("deadline_min"),
                "trigger_alarm_code": result.get("trigger_alarm_code"),
            }
        )
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))


# ============================================================
# SK-04 人工审批 → POST /api/comm/approve
# ============================================================

@router.post("/approve", response_model=ApiResponse)
def decide(payload: ApprovalIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-04 ACT-04 人工审批决策。"""
    # decision_source / approver 由入参透传；超时自动分支由引擎内部硬编码为 SYSTEM / 超时自动。
    ap = decide_approval(
        db,
        approval_code=create_or_get_approval_code(payload.plan_code),
        decision=payload.decision,
        approver=payload.approver,
        decision_source=payload.decision_source,
        reason=payload.reason,
    )
    db.commit()
    return ApiResponse(data=ApprovalOut.model_validate(ap, from_attributes=True))


def create_or_get_approval_code(plan_code: str) -> str:
    """返回审批单编号：APV-{plan_code}。

    真正持久化时由 service 层内部补 -NN 序号后缀，避免同方案重复审批的 PK 冲突。
    """
    return f"APV-{plan_code}"


# ============================================================
# SK-06 修理回执 / 完成 → POST /api/comm/repair
# ============================================================

@router.post("/repair", response_model=ApiResponse)
def recv_repair(payload: RepairReceiveIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-06 ACT-05 修理回执 / 修理完成。"""
    if payload.est_finish_min is None and payload.actual_finish_min is None:
        return ApiResponse(code=400, message="est_finish_min / actual_finish_min 至少传一个")

    # 入参 est/actual_finish_min 是「相对时长」；转换为绝对场景分钟。
    now = payload.as_of_min if payload.as_of_min is not None else get_clock().now_min()
    est_abs = now + payload.est_finish_min if payload.est_finish_min is not None else None
    actual_abs = (
        now + payload.actual_finish_min if payload.actual_finish_min is not None else None
    )
    result = handle_repair_update(
        db,
        order_code=payload.order_code,
        est_finish_min=est_abs,
        actual_finish_min=actual_abs,
        as_of_min=payload.as_of_min,
    )
    db.commit()
    return ApiResponse(
        data=RepairOrderOut.model_validate(result["order"], from_attributes=True)
    )


# ============================================================
# SK-07 链路恢复回迁 → POST /api/comm/restore
# ============================================================

@router.post("/restore", response_model=ApiResponse)
def restore(payload: RestoreIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-07 ACT-06 链路恢复 + 任务回迁 + 释放备用。"""
    result = handle_link_restored(
        db,
        link_code=payload.link_code,
        as_of_min=payload.as_of_min,
    )
    db.commit()
    return ApiResponse(data=result)


# ============================================================
# SK-08 添加任务 → POST /api/comm/task
# ============================================================

@router.post("/task", response_model=ApiResponse)
def add_task(payload: TaskAddIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-08 添加任务（带首条 demand 与归属行）；登记后触发 ACT-02 全局重算。"""
    result = _add_task(
        db,
        {
            "task_code": payload.task_code,
            "task_name": payload.task_name,
            "duration_min": payload.duration_min,
            "critical_min": payload.critical_min,
            "link_code": payload.link_code,
            "demand_gbps": payload.demand_gbps,
            "owner_role": payload.owner_role,
            "lookahead_min": payload.lookahead_min,
        },
    )
    db.commit()
    return ApiResponse(data=result)


# ============================================================
# SK-09 添加链路 → POST /api/comm/link
# ============================================================

@router.post("/link", response_model=ApiResponse)
def add_link(payload: LinkAddIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-09 添加链路；以 0 占用进入资源池；登记后触发 ACT-02 全局重算。"""
    result = _add_link(
        db,
        {
            "link_code": payload.link_code,
            "link_name": payload.link_name,
            "capacity_gbps": payload.capacity_gbps,
            "warning_gbps": payload.warning_gbps,
            "oper_state": payload.oper_state,
            "avg_repair_min": payload.avg_repair_min,
            "lookahead_min": payload.lookahead_min,
            "backup_link_code": payload.backup_link_code,
        },
    )
    db.commit()
    return ApiResponse(data=result)


# ============================================================
# SK-10 需求变更 → POST /api/comm/demand
# ============================================================

@router.post("/demand", response_model=ApiResponse)
def add_demand(payload: DemandIn, db: Session = Depends(get_db)) -> ApiResponse:
    """SK-10 需求变更登记；写入新需求行 + ACT-02 全局重算。"""
    from sqlalchemy.exc import IntegrityError

    from app.models.demand import TrafficDemand

    seq = len(list(db.scalars(select(TrafficDemand)))) + 1
    demand_code = f"D-{payload.task_code[2:]}-{seq:02d}"
    valid_from = payload.valid_from_min if payload.valid_from_min is not None else get_clock().now_min()
    new_d = TrafficDemand(
        demand_code=demand_code,
        task_code=payload.task_code,
        valid_from_min=valid_from,
        demand_gbps=payload.demand_gbps,
        valid_to_min=None,
    )
    db.add(new_d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return ApiResponse(code=400, message=f"需求主键冲突: {demand_code}")
    recalc_all(db, as_of_min=get_clock().now_min())
    db.commit()
    return ApiResponse(
        data={
            "demand_code": demand_code,
            "task_code": payload.task_code,
            "valid_from_min": valid_from,
            "demand_gbps": payload.demand_gbps,
            "triggered_action": "ACT-02",
        }
    )


# ============================================================
# 业务事件流（WS）
# ============================================================

@router.websocket("/ws")
async def comm_ws(ws: WebSocket) -> None:
    """业务 WS：仅做 ack；前端订阅引擎层 /api/scene/ws 即可。"""
    hub = get_hub()
    await hub.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(f"ack: {msg}")
    except WebSocketDisconnect:
        hub.disconnect(ws)