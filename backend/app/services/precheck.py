"""添加任务容量预检：前端表单实时显示"如果加这个任务会不会超限"，不落库。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scene_clock import SceneClock, get_clock
from app.models.demand import TrafficDemand
from app.models.link import CommLink
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding


# ---------- 工具方法 ----------

def _load_link_tasks(
    db: Session, link_code: str
) -> List[Tuple[CommTask, List[TrafficDemand]]]:
    """取该链路当前承载的任务（最新归属折叠）+ 各任务全部需求。"""
    bindings: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == link_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    if not bindings:
        return []
    latest_per_task: Dict[str, TaskLinkBinding] = {}
    for b in bindings:
        latest_per_task.setdefault(b.task_code, b)
    task_codes: List[str] = list(latest_per_task.keys())

    # 只采纳「全局最新归属 == link_code」的任务
    actual_codes: List[str] = []
    for tc in task_codes:
        gl = db.scalar(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.task_code == tc)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            .limit(1)
        )
        if gl is not None and gl.link_code == link_code:
            actual_codes.append(tc)
    if not actual_codes:
        return []

    tasks: List[CommTask] = list(
        db.scalars(select(CommTask).where(CommTask.task_code.in_(actual_codes)))
    )
    demands: List[TrafficDemand] = list(
        db.scalars(select(TrafficDemand).where(TrafficDemand.task_code.in_(actual_codes)))
    )
    demands_by_task: Dict[str, List[TrafficDemand]] = {}
    for d in demands:
        demands_by_task.setdefault(d.task_code, []).append(d)
    return [(t, demands_by_task.get(t.task_code, [])) for t in tasks]


# ---------- 主入口 ----------

def precheck_task(
    db: Session,
    link_code: str,
    demand_gbps: float,
    as_of_min: Optional[int] = None,
) -> Dict[str, Any]:
    """模拟"在 link_code 上新增一个 demand=demand_gbps 的需求"后的占用与预警。

    不写库，仅做算术模拟。

    返回：
        {
            "target_link_code": str,
            "current_after": float,            # 加完后的当前占用 Gbps
            "current_before": float,           # 加上之前的当前占用 Gbps
            "predicted_max_after": float,      # 加完后窗口内最大预测 Gbps
            "capacity_gbps": float,
            "warning_gbps": float,
            "lookahead": int,
            "will_exceed_warning": bool,       # current_after > warning
            "will_exceed_capacity": bool,      # predicted_max_after > capacity
            "message": str,                    # 给前端的提示文案
        }
    """
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    link: Optional[CommLink] = db.get(CommLink, link_code)
    if link is None:
        raise ValueError(f"链路不存在: {link_code}")
    if link.oper_state != "up":
        raise ValueError(f"链路非 up 状态: {link_code} state={link.oper_state}")
    if demand_gbps < 0:
        raise ValueError("demand_gbps 必须 >= 0")

    capacity: float = float(link.capacity_gbps or 0)
    warning: float = float(link.warning_gbps or 0)

    # 1. 链路当前承载任务 + 全部需求
    task_with_demands = _load_link_tasks(db, link_code)
    tasks: List[CommTask] = [t for t, _ in task_with_demands]

    # 2. 前瞻窗口（与 occupancy / forecast 一致）
    link_la: int = link.lookahead_min if link.lookahead_min else 30
    tasks_la: List[int] = [t.lookahead_min if t.lookahead_min else 30 for t in tasks]
    lookahead: int = max([link_la] + tasks_la + [30])
    horizon: int = now + lookahead

    # 3. 当前占用（加需求前 vs 加需求后）
    def _active_demands(demands: List[TrafficDemand], at_min: int) -> float:
        total: float = 0.0
        for d in demands:
            if d.valid_from_min <= at_min and (
                d.valid_to_min is None or at_min < d.valid_to_min
            ):
                total += float(d.demand_gbps or 0)
        return total

    current_before: float = sum(
        _active_demands(d, now) for _, d in task_with_demands
    )
    current_after: float = current_before + float(demand_gbps)

    # 4. 窗口内检查点：now + 所有未来 valid_from_min（含新需求 now）
    checkpoints: Set[int] = {now}
    for _, demands in task_with_demands:
        for d in demands:
            if now < d.valid_from_min <= horizon:
                checkpoints.add(d.valid_from_min)

    # 模拟新需求：now 起持续有效（valid_to_min=None），valid_from_min = now
    sim_demand = TrafficDemand(
        demand_code="__sim__",
        task_code="__sim__",
        valid_from_min=now,
        demand_gbps=float(demand_gbps),
        valid_to_min=None,
    )

    # 5. 逐检查点求 predicted_load（严格 > capacity 取首个命中；这里只要 max）
    predicted_max: float = 0.0
    for m_prime in sorted(checkpoints):
        total: float = 0.0
        for _, demands in task_with_demands:
            for d in demands:
                if d.valid_from_min <= m_prime and (
                    d.valid_to_min is None or m_prime < d.valid_to_min
                ):
                    total += float(d.demand_gbps or 0)
        # 叠加新需求
        if (
            sim_demand.valid_from_min <= m_prime
            and (sim_demand.valid_to_min is None or m_prime < sim_demand.valid_to_min)
        ):
            total += float(sim_demand.demand_gbps or 0)
        if total > predicted_max:
            predicted_max = total

    will_exceed_capacity: bool = predicted_max > capacity
    will_exceed_warning: bool = current_after > warning

    # 6. 文案
    if will_exceed_capacity:
        message = (
            f"{link_code} 当前 {current_before:.2f}G + {demand_gbps:.2f}G = "
            f"{current_after:.2f}G > {capacity:.2f}G。可以登记，"
            f"登记后会进入方案审批流程。"
        )
    elif will_exceed_warning:
        message = (
            f"{link_code} 当前 {current_before:.2f}G + {demand_gbps:.2f}G = "
            f"{current_after:.2f}G > {warning:.2f}G 预警线。"
            f"建议加容量备用链路或下调需求。"
        )
    else:
        message = "容量充足，可直接登记。"

    return {
        "target_link_code": link_code,
        "current_after": round(current_after, 2),
        "current_before": round(current_before, 2),
        "predicted_max_after": round(predicted_max, 2),
        "capacity_gbps": capacity,
        "warning_gbps": warning,
        "lookahead": lookahead,
        "will_exceed_warning": will_exceed_warning,
        "will_exceed_capacity": will_exceed_capacity,
        "message": message,
    }
