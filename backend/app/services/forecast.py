"""前瞻预测逐分钟数据（阶梯点采样）。"""
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

    # 进一步只保留"全局最新归属 == link_code"的任务
    actual_codes: List[str] = []
    for tc in task_codes:
        global_latest = db.scalar(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.task_code == tc)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            .limit(1)
        )
        if global_latest is not None and global_latest.link_code == link_code:
            actual_codes.append(tc)
    if not actual_codes:
        return []

    tasks: List[CommTask] = list(
        db.scalars(select(CommTask).where(CommTask.task_code.in_(actual_codes)))
    )
    demands: List[TrafficDemand] = list(
        db.scalars(
            select(TrafficDemand).where(TrafficDemand.task_code.in_(actual_codes))
        )
    )
    demands_by_task: Dict[str, List[TrafficDemand]] = {}
    for d in demands:
        demands_by_task.setdefault(d.task_code, []).append(d)
    return [(t, demands_by_task.get(t.task_code, [])) for t in tasks]


def _load_outside_min(
    db: Session,
    link_code: str,
    now: int,
    horizon: int,
    capacity: float,
) -> Optional[int]:
    """窗口外但有 future valid_from_min 的最早超限分钟（用于"灰点提示"）。

    仅检测未在 [now, now+horizon] 内的 demand.valid_from_min 中，
    累计到该分钟时是否 > capacity。
    """
    bindings = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == link_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    if not bindings:
        return None
    latest: Dict[str, TaskLinkBinding] = {}
    for b in bindings:
        latest.setdefault(b.task_code, b)
    candidates: List[Tuple[CommTask, List[TrafficDemand]]] = []
    for tc, b in latest.items():
        gl = db.scalar(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.task_code == tc)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            .limit(1)
        )
        if gl is not None and gl.link_code == link_code:
            ts = list(
                db.scalars(
                    select(CommTask).where(CommTask.task_code == tc).limit(1)
                )
            )
            t = ts[0] if ts else None
            if t is not None:
                demands = list(
                    db.scalars(
                        select(TrafficDemand).where(TrafficDemand.task_code == tc)
                    )
                )
                candidates.append((t, demands))
    if not candidates:
        return None
    future_starts: List[int] = []
    for _, demands in candidates:
        for d in demands:
            if d.valid_from_min > now + horizon:
                future_starts.append(d.valid_from_min)
    if not future_starts:
        return None
    for m_prime in sorted(set(future_starts)):
        total = 0.0
        for _, demands in candidates:
            for d in demands:
                if d.valid_from_min <= m_prime and (
                    d.valid_to_min is None or m_prime < d.valid_to_min
                ):
                    total += float(d.demand_gbps or 0)
        if total > capacity:
            return m_prime
    return None


# ---------- 主入口 ----------

def get_forecast(
    db: Session,
    link_code: str,
    as_of_min: Optional[int] = None,
) -> Dict[str, Any]:
    """返回链路在 [now, now+lookahead] 内的阶梯式 predicted_load 采样。

    返回：
        {
            "link_code": str,
            "now": int,
            "lookahead": int,
            "warning_gbps": float,
            "capacity_gbps": float,
            "points": [{"min": int, "gbps": float}, ...],   # 阶梯点
            "hit_min": int | None,                          # 窗口内首个 > capacity
            "hit_gbps": float | None,
            "outside_min": int | None,                      # 窗口外首个 > capacity
        }
    """
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    link: Optional[CommLink] = db.get(CommLink, link_code)
    if link is None:
        raise ValueError(f"链路不存在: {link_code}")

    capacity: float = float(link.capacity_gbps or 0)
    warning: float = float(link.warning_gbps or 0)

    # 1.0 链路 down 短路：down 后业务上不再承载任何 demand，返回空 points
    #     而非报错或返回陈旧预测。hit_min / outside_min 均为 None。
    if link.oper_state != "up":
        return {
            "link_code": link_code,
            "now": now,
            "lookahead": 0,
            "warning_gbps": warning,
            "capacity_gbps": capacity,
            "points": [],
            "hit_min": None,
            "hit_gbps": None,
            "outside_min": None,
        }

    # 1. 链路当前承载任务 + 全部需求
    task_with_demands = _load_link_tasks(db, link_code)
    tasks: List[CommTask] = [t for t, _ in task_with_demands]

    # 2. 前瞻窗口
    link_la: int = link.lookahead_min if link.lookahead_min else 30
    tasks_la: List[int] = [t.lookahead_min if t.lookahead_min else 30 for t in tasks]
    lookahead: int = max([link_la] + tasks_la + [30])

    horizon: int = now + lookahead

    # 3. 收集检查点：每个需求 valid_from_min ∈ (now, horizon] 必加入；起点 now 也加入
    checkpoints: Set[int] = {now}
    for _, demands in task_with_demands:
        for d in demands:
            if now < d.valid_from_min <= horizon:
                checkpoints.add(d.valid_from_min)

    # 4. 阶梯点采样：合并"相等值"的相邻段，只保留变化点
    points: List[Dict[str, Any]] = []
    hit_min: Optional[int] = None
    hit_gbps: Optional[float] = None
    last_value: Optional[float] = None

    for m_prime in sorted(checkpoints):
        # 在 m_prime 时刻生效的总需求
        total: float = 0.0
        for _, demands in task_with_demands:
            for d in demands:
                if d.valid_from_min <= m_prime and (
                    d.valid_to_min is None or m_prime < d.valid_to_min
                ):
                    total += float(d.demand_gbps or 0)
        total = round(total, 2)
        # 阶梯点：只在新值出现时入列
        if last_value is None or total != last_value:
            points.append({"min": m_prime, "gbps": total})
            last_value = total
        # 命中判定（严格大于）
        if hit_min is None and total > capacity:
            hit_min = m_prime
            hit_gbps = total

    # 5. 窗口外探测
    outside_min: Optional[int] = _load_outside_min(
        db, link_code=link_code, now=now, horizon=lookahead, capacity=capacity
    )

    return {
        "link_code": link_code,
        "now": now,
        "lookahead": lookahead,
        "warning_gbps": warning,
        "capacity_gbps": capacity,
        "points": points,
        "hit_min": hit_min,
        "hit_gbps": hit_gbps,
        "outside_min": outside_min,
    }
