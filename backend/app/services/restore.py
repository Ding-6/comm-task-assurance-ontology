"""ACT-06 链路恢复与任务回迁。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.scene_clock import SceneClock, get_clock
from app.models.demand import TrafficDemand
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding
from app.services.occupancy import calc_occupancy, recalc_all


# ---------- 工具方法 ----------

def _active_demand(db: Session, task_code: str, at_min: int) -> float:
    """任务在 at_min 时刻的活跃需求速率。"""
    rows: List[TrafficDemand] = list(
        db.scalars(
            select(TrafficDemand).where(TrafficDemand.task_code == task_code)
        )
    )
    g: float = 0.0
    for d in rows:
        if d.valid_from_min > at_min:
            continue
        if d.valid_to_min is not None and at_min >= d.valid_to_min:
            continue
        g += float(d.demand_gbps or 0)
    return g


def _candidates(db: Session, link_code: str) -> List[TaskLinkBinding]:
    """回迁候选：曾经 link_code=本链路、但最新归属不在本链路的任务。

    思路：取该链路历史上有过归属的所有 task_code（distinct），排除当前
    最新归属仍是本链路的，剩下的就是「本链路原始任务、现在被迁走」的清单。
    """
    all_bindings: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == link_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    if not all_bindings:
        return []

    # 这些 task_code 中，筛选出「最新一次归属不是本链路」的任务
    task_codes: Set[str] = {b.task_code for b in all_bindings}
    candidates: List[TaskLinkBinding] = []
    for tc in task_codes:
        # 找到该 task_code 全局最新一条
        latest: Optional[TaskLinkBinding] = db.scalar(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.task_code == tc)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            .limit(1)
        )
        if latest is not None and latest.link_code != link_code:
            candidates.append(latest)
    return candidates


def _current_load_on_link(db: Session, link_code: str, at_min: int) -> float:
    """链路当前 at_min 时刻的实时占用（仅计「全局最新」归属在本链路的任务）。"""
    # 收集曾经在本链路出现过的 task_code
    candidate_task_codes: Set[str] = set(
        db.scalars(
            select(TaskLinkBinding.task_code)
            .where(TaskLinkBinding.link_code == link_code)
            .distinct()
        )
    )
    if not candidate_task_codes:
        return 0.0
    # 过滤：只保留「全局最新归属 == link_code」的任务
    actual_task_codes: List[str] = []
    for tc in candidate_task_codes:
        global_latest = db.scalar(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.task_code == tc)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            .limit(1)
        )
        if global_latest is not None and global_latest.link_code == link_code:
            actual_task_codes.append(tc)
    total: float = 0.0
    for tc in actual_task_codes:
        total += _active_demand(db, tc, at_min)
    return total


# ---------- 主流程 ----------

def handle_link_restored(
    db: Session, link_code: str, as_of_min: Optional[int] = None
) -> Dict[str, Any]:
    """链路恢复后回迁任务。

    返回：
        {
            "link_code": link_code,
            "restored_tasks": [task_code, ...],
            "skipped_tasks": [{task_code, reason}, ...],
            "released_links": [link_code, ...],   # 因回迁腾空的原承载链路
            "released_link_code": link_code | None,  # 兼容旧返回
        }
    """
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    # 1. 校验链路存在 + up
    link: Optional[CommLink] = db.get(CommLink, link_code)
    if link is None:
        raise ValueError(f"链路不存在: {link_code}")
    if link.oper_state != "up":
        # 软处理：把链路置 up（恢复通知），再继续回迁流程
        prev_state: str = link.oper_state
        link.oper_state = "up"
        db.add(
            SceneEvent(
                event_code=f"EVT-RS-UP-{datetime.now().strftime('%H%M%S%f')}",
                event_type="state_changed",
                ref_type="link",
                ref_code=link_code,
                occur_min=now,
                summary=f"{link_code} {prev_state} -> up（恢复通知）",
            )
        )
        db.flush()
        from app.services.engine import safe_push

        safe_push(
            "toast",
            {
                "level": "info",
                "message": f"{link_code} {prev_state} -> up",
                "link_code": link_code,
            },
        )
        # 不 return，继续往下走正常的回迁候选扫描

    capacity: float = float(link.capacity_gbps or 0)
    warning: float = float(link.warning_gbps or 0)

    # 2. 候选任务
    cands = _candidates(db, link_code)
    if not cands:
        # 没有可回迁任务，也要写事件 + 重算 + 推送
        _after_restore(db, link_code, [], [], now)
        return {
            "link_code": link_code,
            "restored_tasks": [],
            "skipped_tasks": [],
            "released_links": [],
            "released_link_code": link_code,
        }

    # 3. 容量校验 + 逐任务回迁
    current_load: float = _current_load_on_link(db, link_code, now)
    restored: List[str] = []
    skipped: List[Dict[str, str]] = []
    original_holders: Set[str] = set()  # 收集被回迁走任务的原承载链路

    for cand in cands:
        task_code: str = cand.task_code
        original_link: str = cand.link_code
        task_demand: float = _active_demand(db, task_code, now)
        if current_load + task_demand > capacity:
            # 容量不允许，留在原链路
            skipped.append(
                {"task_code": task_code, "reason": f"超容量({current_load + task_demand}>{capacity})"}
            )
            continue

        # 4. 写新归属
        db.add(
            TaskLinkBinding(
                task_code=task_code,
                link_code=link_code,
                assigned_min=now,
                note=f"{link_code} 修复完成，由原承载链路回迁",
            )
        )
        task: Optional[CommTask] = db.get(CommTask, task_code)
        if task is not None:
            task.current_link_code = link_code
        restored.append(task_code)
        current_load += task_demand
        original_holders.add(original_link)

    # 5. 收尾（事件 + 占用重算 + ws）
    _after_restore(db, link_code, restored, skipped, now)

    # 备用释放检测：原承载链路若无任何任务承载，则视为已释放
    released_links: List[str] = []
    for holder in original_holders:
        if holder == link_code:
            continue
        holder_bindings = list(
            db.scalars(
                select(TaskLinkBinding)
                .where(TaskLinkBinding.link_code == holder)
                .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            )
        )
        # 折叠：每个 task_code 取 holder 上「最新」一条；并验证它的「全局最新」就是 holder
        # 否则只算历史，不算「当前还有任务」
        seen: Set[str] = set()
        any_task: bool = False
        for b in holder_bindings:
            if b.task_code in seen:
                continue
            seen.add(b.task_code)
            global_latest = db.scalar(
                select(TaskLinkBinding)
                .where(TaskLinkBinding.task_code == b.task_code)
                .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
                .limit(1)
            )
            if global_latest is not None and global_latest.link_code == holder:
                any_task = True
                break
        if not any_task:
            released_links.append(holder)
            # 把 holder 的占用字段清零（可视为释放）
            holder_link: Optional[CommLink] = db.get(CommLink, holder)
            if holder_link is not None:
                holder_link.current_load_gbps = 0.0
                holder_link.future_load_gbps = 0.0
                if holder_link.warn_status in ("超预警线", "超容量"):
                    holder_link.warn_status = "正常"

    return {
        "link_code": link_code,
        "restored_tasks": restored,
        "skipped_tasks": skipped,
        "released_links": released_links,
        "released_link_code": link_code,
    }


def _after_restore(
    db: Session,
    link_code: str,
    restored: List[str],
    skipped: List[Dict[str, str]],
    now: int,
) -> None:
    """回迁收尾：写事件、占用重算、ws 推送。"""
    # 6. 写 link_restored 事件
    summary: str = (
        f"{link_code} 恢复，"
        f"回迁 {len(restored)} 个任务，"
        f"跳过 {len(skipped)} 个"
    )
    db.add(
        SceneEvent(
            event_code=f"EVT-RS-{datetime.now().strftime('%H%M%S%f')}",
            event_type="link_restored",
            ref_type="link",
            ref_code=link_code,
            occur_min=now,
            summary=summary,
        )
    )
    db.flush()

    # 8. 全局重算
    recalc_all(db, as_of_min=now)
    db.flush()

    # 7. ws 顶部提示条
    msg: str = (
        f"{link_code} 已恢复"
        + (f"，任务回迁完成（{len(restored)} 个）" if restored else "（无任务回迁）")
    )

    from app.services.engine import safe_push

    safe_push(
        "toast",
        {"level": "info", "message": msg, "link_code": link_code},
    )


# ---------- 兼容旧接口 ----------

def restore_link(db: Session, link_code: str) -> int:
    """兼容旧调用：返回回迁任务数。"""
    result = handle_link_restored(db, link_code)
    return len(result.get("restored_tasks", []))
