"""T+120 全窗口证据核对报告：场景结束后汇总所有证据供画板07展示。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alarm import ResourceAlarm
from app.models.approval import ApprovalRecord
from app.models.event import SceneEvent
from app.models.plan import CommPlan
from app.models.repair_order import RepairOrder
from app.models.task_link import TaskLinkBinding


# 时间轴上视为「人工介入节点」的事件类型
_MANUAL_EVENT_TYPES: set[str] = {"plan_generated", "approval_decided"}

# 相邻事件分钟差 > 5 视为断点
_GAP_THRESHOLD_MIN: int = 5


def _check_event_continuity(events: List[SceneEvent]) -> Dict[str, Any]:
    """事件连续性核对：相邻 occur_min 差 > 5 视为有断点。"""
    sorted_events: List[SceneEvent] = sorted(events, key=lambda e: (e.occur_min, e.event_code))
    total: int = len(sorted_events)
    gap_minutes: List[int] = []
    for prev, curr in zip(sorted_events, sorted_events[1:]):
        diff: int = int(curr.occur_min) - int(prev.occur_min)
        if diff > _GAP_THRESHOLD_MIN:
            gap_minutes.append(int(prev.occur_min))
    return {
        "total": total,
        "has_gap": bool(gap_minutes),
        "gap_at_min": gap_minutes,
        "result": "有断点" if gap_minutes else "连续",
    }


def _build_task_history(db: Session) -> List[Dict[str, Any]]:
    """任务归属历史：按 task_code 分组，按 assigned_min 排序。"""
    bindings: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .order_by(
                TaskLinkBinding.task_code.asc(),
                TaskLinkBinding.assigned_min.asc(),
                TaskLinkBinding.id.asc(),
            )
        )
    )
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    task_order: List[str] = []
    for b in bindings:
        if b.task_code not in grouped:
            task_order.append(b.task_code)
        grouped[b.task_code].append(
            {
                "assigned_min": int(b.assigned_min),
                "link_code": b.link_code,
                "note": b.note or "",
            }
        )
    return [
        {"task_code": tc, "history": grouped[tc]} for tc in task_order
    ]


def _build_approval_records(db: Session) -> List[Dict[str, Any]]:
    records: List[ApprovalRecord] = list(
        db.scalars(select(ApprovalRecord).order_by(ApprovalRecord.decided_min.asc()))
    )
    return [
        {
            "approval_code": r.approval_code,
            "plan_code": r.plan_code,
            "decision": r.decision or "",
            "approver": r.approver or "",
            "decision_source": r.decision_source or "",
            "decided_min": int(r.decided_min) if r.decided_min is not None else None,
            "reason": r.reason or "",
        }
        for r in records
    ]


def _build_final_states(db: Session) -> Dict[str, Any]:
    plans: List[CommPlan] = list(
        db.scalars(
            select(CommPlan).order_by(CommPlan.generated_min.asc().nullslast())
        )
    )
    repair_orders: List[RepairOrder] = list(
        db.scalars(
            select(RepairOrder).order_by(RepairOrder.request_min.asc().nullslast())
        )
    )
    alarms: List[ResourceAlarm] = list(
        db.scalars(
            select(ResourceAlarm).order_by(ResourceAlarm.event_min.asc().nullslast())
        )
    )
    return {
        "plans": [
            {
                "plan_code": p.plan_code,
                "alarm_code": p.alarm_code,
                "plan_type": p.plan_type,
                "link_code": p.link_code,
                "target_link_code": p.target_link_code,
                "status": p.status or "",
                "is_default": p.is_default or "",
                "can_meet_critical": p.can_meet_critical or "",
                "generated_min": int(p.generated_min) if p.generated_min is not None else None,
            }
            for p in plans
        ],
        "repair_orders": [
            {
                "order_code": o.order_code,
                "link_code": o.link_code,
                "alarm_code": o.alarm_code,
                "request_min": int(o.request_min) if o.request_min is not None else None,
                "est_finish_min": (
                    int(o.est_finish_min) if o.est_finish_min is not None else None
                ),
                "actual_finish_min": (
                    int(o.actual_finish_min) if o.actual_finish_min is not None else None
                ),
                "status": o.status or "",
            }
            for o in repair_orders
        ],
        "alarms": [
            {
                "alarm_code": a.alarm_code,
                "link_code": a.link_code,
                "alarm_type": a.alarm_type or "",
                "native_severity": a.native_severity or "",
                "event_min": int(a.event_min) if a.event_min is not None else None,
                "predicted_min": (
                    int(a.predicted_min) if a.predicted_min is not None else None
                ),
            }
            for a in alarms
        ],
    }


def _build_timeline(db: Session) -> List[Dict[str, Any]]:
    """时间轴：全部事件按 occur_min 升序，标记是否人工介入节点。"""
    events: List[SceneEvent] = list(
        db.scalars(
            select(SceneEvent).order_by(
                SceneEvent.occur_min.asc(), SceneEvent.event_code.asc()
            )
        )
    )
    return [
        {
            "occur_min": int(e.occur_min),
            "event_type": e.event_type or "",
            "summary": e.summary or "",
            "is_manual_node": (e.event_type or "") in _MANUAL_EVENT_TYPES,
        }
        for e in events
    ]


def get_evidence_report(db: Session) -> Dict[str, Any]:
    """T+120 全窗口证据核对报告。

    返回：
        {
            "event_continuity": { total, has_gap, gap_at_min, result },
            "task_history": [ { task_code, history: [...] } ],
            "approval_records": [ { approval_code, ... } ],
            "final_states": { plans, repair_orders, alarms },
            "timeline": [ { occur_min, event_type, summary, is_manual_node } ],
        }
    """
    events: List[SceneEvent] = list(db.scalars(select(SceneEvent)))

    return {
        "event_continuity": _check_event_continuity(events),
        "task_history": _build_task_history(db),
        "approval_records": _build_approval_records(db),
        "final_states": _build_final_states(db),
        "timeline": _build_timeline(db),
    }
