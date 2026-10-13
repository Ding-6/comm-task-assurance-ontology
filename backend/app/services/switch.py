"""ACT-01 链路故障识别与自动切换。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.scene_clock import SceneClock, get_clock
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.repair_order import RepairOrder
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding
from app.services.occupancy import calc_occupancy, recalc_all


def _load_fault_tasks(
    db: Session, link_code: str
) -> List[TaskLinkBinding]:
    """取该链路当前承载的任务（按 task_code 折叠到最新 assigned_min）。"""
    rows: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == link_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    latest: Dict[str, TaskLinkBinding] = {}
    for r in rows:
        latest.setdefault(r.task_code, r)
    return list(latest.values())


def _next_repair_seq(db: Session, link_code: str) -> int:
    """取该链路当前已存在的修理单数 +1。"""
    rows = list(
        db.scalars(select(RepairOrder).where(RepairOrder.link_code == link_code))
    )
    return len(rows) + 1


def _pick_target_link(
    db: Session, fault: CommLink
) -> Optional[CommLink]:
    """选择切换目标。

    优先级：
    1. 共享链路：oper_state='up'、current_load_gbps>0 的非 fault、非 backup 的链路
       → 在其中取 current_load 最低的（剩余容量最大）
    2. 备用链路：fault.backup_link_code（仅当共享链路不可用 / 无候选时回退）
    """
    # 所有可用候选
    up_links: List[CommLink] = list(
        db.scalars(
            select(CommLink).where(
                CommLink.link_code != fault.link_code,
                CommLink.oper_state == "up",
            )
        )
    )

    # 1. 共享链路：current_load > 0 的链路
    shared: List[CommLink] = [l for l in up_links if l.current_load_gbps and l.current_load_gbps > 0]
    if shared:
        return sorted(shared, key=lambda l: float(l.current_load_gbps or 0))[0]

    # 2. 没有任何「当前在跑」任务的共享链路时，回退到 backup
    if fault.backup_link_code:
        backup = db.get(CommLink, fault.backup_link_code)
        if backup is not None and backup.oper_state == "up":
            return backup

    # 3. 再退一步：所有 up 链路中 current_load 最低的
    if up_links:
        return sorted(up_links, key=lambda l: float(l.current_load_gbps or 0))[0]

    return None


def handle_link_down(
    db: Session, alarm_link_code: str, as_of_min: Optional[int] = None
) -> Dict[str, Any]:
    """识别资源异常并自动切换链路承载。

    返回：
        {
            "switched_tasks": [...],
            "repair_order_code": "RP-...",
            "from_link": alarm_link_code,
            "to_link": target_link_code,
        }
    """
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    # 0. 取故障链路
    fault: Optional[CommLink] = db.get(CommLink, alarm_link_code)
    if fault is None:
        raise ValueError(f"链路不存在: {alarm_link_code}")

    # 幂等检查：若该链路已经 down 且无任务承载 -> 直接返回
    if fault.oper_state == "down":
        bindings = _load_fault_tasks(db, alarm_link_code)
        # bindings 里只包含「最新归属是本链路」的任务，若为空说明已迁完
        if not bindings:
            return {
                "switched_tasks": [],
                "repair_order_code": "",
                "from_link": alarm_link_code,
                "to_link": None,
            }

    # 1. 把 fault 置 down
    fault.oper_state = "down"

    # 2. 取出 fault 承载的任务
    bindings = _load_fault_tasks(db, alarm_link_code)
    task_codes: List[str] = [b.task_code for b in bindings]
    if not task_codes:
        target_link: Optional[CommLink] = None
    else:
        # 3. 选择切换目标
        target_link = _pick_target_link(db, fault)
        if target_link is None:
            raise ValueError(f"无可用目标链路: {alarm_link_code}")

        # 4. 逐任务写入新归属 + 更新 current_link_code
        for b in bindings:
            db.add(
                TaskLinkBinding(
                    task_code=b.task_code,
                    link_code=target_link.link_code,
                    assigned_min=now,
                    note=f"由 {alarm_link_code} 切换而来",
                )
            )
            task: Optional[CommTask] = db.get(CommTask, b.task_code)
            if task is not None:
                task.current_link_code = target_link.link_code

    # 5. 写修理请求
    seq = _next_repair_seq(db, alarm_link_code)
    order = RepairOrder(
        order_code=f"RP-{alarm_link_code}-{seq:03d}",
        link_code=alarm_link_code,
        alarm_code=None,
        request_min=now,
        est_finish_min=fault.avg_repair_min,
        status="已申请",
    )
    db.add(order)

    # 6. 写 switch_done 事件
    db.add(
        SceneEvent(
            event_code=f"EVT-SW-{datetime.now().strftime('%H%M%S%f')}",
            event_type="switch_done",
            ref_type="link",
            ref_code=alarm_link_code,
            occur_min=now,
            summary=(
                f"{alarm_link_code} 中断，{len(task_codes)} 个任务切换至 "
                f"{target_link.link_code if target_link else '无'}"
            ),
        )
    )

    # 7. 切换完成后递归重算占用
    if target_link is not None:
        calc_occupancy(db, target_link.link_code, as_of_min=now)
    calc_occupancy(db, alarm_link_code, as_of_min=now)
    recalc_all(db, as_of_min=now)
    db.flush()

    # 8. ws 推送 modal_notice
    if target_link is not None and task_codes:
        title = "链路中断"
        message = (
            f"{alarm_link_code} 链路中断，"
            f"{len(task_codes)} 个任务已自动切换至 {target_link.link_code} 链路"
        )
    elif target_link is not None:
        title = "链路中断"
        message = f"{alarm_link_code} 链路中断（无承载任务）"
    else:
        title = "链路中断"
        message = f"{alarm_link_code} 链路中断，无可用目标链路"

    from app.services.engine import safe_push

    safe_push(
        "modal_notice",
        {"title": title, "message": message, "level": "info"},
    )

    # 9. 返回
    return {
        "switched_tasks": task_codes,
        "repair_order_code": order.order_code,
        "from_link": alarm_link_code,
        "to_link": target_link.link_code if target_link else None,
    }


# ---------- 兼容旧接口 ----------

def switch_due_to_link_down(
    db: Session, link_code: str, reason: str = "链路故障切换"
) -> int:
    """兼容旧调用：返回切换任务数。"""
    return len(handle_link_down(db, link_code).get("switched_tasks", []))
