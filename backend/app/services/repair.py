"""ACT-05 修理单申请 + 回执评估。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.scene_clock import SceneClock, get_clock
from app.models.alarm import ResourceAlarm
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.plan import CommPlan
from app.models.repair_order import RepairOrder
from app.models.task import CommTask
from app.services.restore import restore_link


# ---------- 工具方法 ----------

def _next_order_seq(db: Session, link_code: str) -> int:
    """本链路已存在修理单数 +1。"""
    rows = list(
        db.scalars(select(RepairOrder).where(RepairOrder.link_code == link_code))
    )
    return len(rows) + 1


def _critical_deadline(db: Session) -> int:
    """所有任务 critical_min 的最小非空值（缺省 50）。"""
    rows = list(
        db.scalars(select(CommTask.critical_min).where(CommTask.critical_min.is_not(None)))
    )
    return min(rows) if rows else 50


# ---------- 申请 ----------

def request_repair(
    db: Session, alarm_code: str, plan_code: Optional[str] = None
) -> RepairOrder:
    """申请一张修理单（已申请），由外部系统回执 est_finish。"""
    clock = get_clock()
    now = clock.now_min()

    alarm: Optional[ResourceAlarm] = db.get(ResourceAlarm, alarm_code)
    if alarm is None:
        raise ValueError(f"告警不存在: {alarm_code}")

    link: Optional[CommLink] = db.get(CommLink, alarm.link_code)
    if link is None:
        raise ValueError(f"链路不存在: {alarm.link_code}")

    seq = _next_order_seq(db, alarm.link_code)
    order = RepairOrder(
        order_code=f"RP-{alarm.link_code}-{seq:03d}",
        link_code=alarm.link_code,
        alarm_code=alarm_code,
        request_min=now,
        est_finish_min=link.avg_repair_min,
        status="已申请",
    )
    db.add(order)
    db.add(
        SceneEvent(
            event_code=f"EVT-RO-{datetime.now().strftime('%H%M%S%f')}",
            event_type="repair_received",
            ref_type="repair_order",
            ref_code=order.order_code,
            occur_min=now,
            summary=f"已申请修理 {order.order_code}",
        )
    )
    db.flush()
    return order


# ---------- 主流程：handle_repair_update ----------

def handle_repair_update(
    db: Session,
    order_code: str,
    est_finish_min: Optional[int] = None,
    actual_finish_min: Optional[int] = None,
    as_of_min: Optional[int] = None,
) -> Dict[str, Any]:
    """处理修理回执/完成。

    两种用法：
    - 回执：传 est_finish_min
    - 完成：传 actual_finish_min（会触发 ACT-06 链路恢复回迁）

    返回：
        {
            "order": RepairOrder,
            "event_type": "repair_received" | "link_restored",
            "plans_updated": [CommPlan, ...],   # 受回执影响的方案
        }
    """
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    order: Optional[RepairOrder] = db.get(RepairOrder, order_code)
    if order is None:
        raise ValueError(f"修理单不存在: {order_code}")

    plans_updated: List[CommPlan] = []
    event_type: str = "repair_received"

    # ---------- 1. 回执 ----------
    if est_finish_min is not None:
        order.est_finish_min = est_finish_min
        order.status = "已回执"

        # 1.1 找到该链路上的全部待审批方案
        pending_plans: List[CommPlan] = list(
            db.scalars(
                select(CommPlan).where(
                    CommPlan.link_code == order.link_code,
                    CommPlan.status == "待审批",
                )
            )
        )

        if pending_plans:
            dead_line: int = _critical_deadline(db)
            for p in pending_plans:
                if p.plan_type != "repair":
                    continue
                # est_finish_min 与 dead_line 都是「场景绝对分钟」
                if est_finish_min <= dead_line:
                    p.can_meet_critical = "是"
                else:
                    p.can_meet_critical = "否"
                    p.status = "已作废"
                plans_updated.append(p)

        # 1.2 写事件
        db.add(
            SceneEvent(
                event_code=f"EVT-ROA-{datetime.now().strftime('%H%M%S%f')}",
                event_type="repair_received",
                ref_type="repair_order",
                ref_code=order_code,
                occur_min=now,
                summary=(
                    f"修理回执 {order_code} est_finish={est_finish_min} "
                    f"now={now} dead_line={_critical_deadline(db)}"
                ),
            )
        )
        db.flush()

        # 1.3 ws 推送 modal_refresh（不重置倒计时）
        if pending_plans:
            from app.services.engine import safe_push

            # 完整 plan dict（与 modal_approval 同结构）
            payload_plans: List[Dict[str, Any]] = [
                {
                    "plan_code": p.plan_code,
                    "plan_type": p.plan_type,
                    "is_default": p.is_default,
                    "can_meet_critical": p.can_meet_critical,
                    "predicted_load_after_gbps": float(p.predicted_load_after_gbps or 0),
                    "status": p.status,
                    "recommendation": p.recommendation,
                    "target_link_code": p.target_link_code,
                    "est_repair_min": p.est_repair_min,
                }
                for p in pending_plans
            ]

            # 推断 fresh_message
            dead_line_msg: int = _critical_deadline(db)
            if est_finish_min > dead_line_msg:
                # 修理时间晚于关键期 → 提示切备用
                fresh_message: str = (
                    f"修理单预计T+{est_finish_min}完成，晚于关键期T+{dead_line_msg}，"
                    f"转备用为唯一可行方案。倒计时不重置。"
                )
            else:
                fresh_message = (
                    f"修理单预计T+{est_finish_min}完成，关键期T+{dead_line_msg}可赶上，"
                    f"倒计时不重置。"
                )

            # 上下文：与 modal_approval 一致，但 fresh_message 覆盖
            cap_alarm = db.scalar(
                select(CommPlan).where(
                    CommPlan.link_code == order.link_code,
                    CommPlan.status == "待审批",
                )
            )  # 取一个占位 cap_alarm 拿 alarm_code 字段用
            ctx_alarm_code: Optional[str] = None
            if cap_alarm is not None:
                ctx_alarm_code = cap_alarm.alarm_code

            safe_push(
                "modal_refresh",
                {
                    "order_code": order_code,
                    "link_code": order.link_code,
                    "alarm_code": ctx_alarm_code,
                    "est_finish_min": est_finish_min,
                    "deadline_min": dead_line_msg,
                    "plans": payload_plans,
                    "fresh_message": fresh_message,
                    "reset_countdown": False,
                },
            )

    # ---------- 2. 完成 ----------
    if actual_finish_min is not None:
        order.actual_finish_min = actual_finish_min
        order.status = "已完成"
        event_type = "link_restored"

        link: Optional[CommLink] = db.get(CommLink, order.link_code)
        if link is not None:
            link.oper_state = "up"

        db.add(
            SceneEvent(
                event_code=f"EVT-DN-{datetime.now().strftime('%H%M%S%f')}",
                event_type="state_changed",
                ref_type="link",
                ref_code=order.link_code,
                occur_min=now,
                summary=f"{order.link_code} 修复完成，恢复 up",
            )
        )
        db.flush()

        # 触发 ACT-06 任务回迁
        try:
            restore_link(db, order.link_code)
        except Exception:
            # 回迁失败不影响主流程
            pass

    return {
        "order": order,
        "event_type": event_type,
        "plans_updated": plans_updated,
    }


# ---------- 兼容旧接口 ----------

def evaluate_repair_receipt(
    db: Session, order_code: str, est_finish_min: int
) -> RepairOrder:
    """兼容旧调用：仅处理回执。"""
    result = handle_repair_update(db, order_code, est_finish_min=est_finish_min)
    return result["order"]
