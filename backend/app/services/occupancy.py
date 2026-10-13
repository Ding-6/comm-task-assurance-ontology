"""ACT-02 链路占用计算 + 前瞻预警（容量超限告警 + ws toast）。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.scene_clock import SceneClock, get_clock
from app.models.alarm import ResourceAlarm
from app.models.demand import TrafficDemand
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.plan import CommPlan
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding


# ---------- 工具方法 ----------

def _gen_alarm_code() -> str:
    """生成不依赖数据库 count 的告警主键，避免并发主键冲突。"""
    return f"AL-{uuid.uuid4().hex[:8].upper()}"


def _active_demand_gbps(db: Session, task_code: str, at_min: int) -> float:
    """任务在 at_min 时刻的活跃需求速率。"""
    rows: List[TrafficDemand] = list(
        db.scalars(select(TrafficDemand).where(TrafficDemand.task_code == task_code))
    )
    g: float = 0.0
    for d in rows:
        if d.valid_from_min > at_min:
            continue
        if d.valid_to_min is not None and at_min >= d.valid_to_min:
            continue
        g += float(d.demand_gbps or 0)
    return g


def _load_link_tasks(
    db: Session, link_code: str
) -> List[Tuple[CommTask, List[TrafficDemand]]]:
    """读取该链路当前承载的所有任务，每个任务带出其全部需求。"""
    # 1. 取出所有 comm_task_link 中 link_code 等于本链路的记录
    bindings: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == link_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    if not bindings:
        return []

    # 2. 每个 task_code 取 assigned_min 最大的一行（最新归属）
    latest_per_task: Dict[str, TaskLinkBinding] = {}
    for b in bindings:
        latest_per_task.setdefault(b.task_code, b)

    # 3. 取这些任务及其全部需求
    task_codes: List[str] = list(latest_per_task.keys())
    tasks: List[CommTask] = list(
        db.scalars(select(CommTask).where(CommTask.task_code.in_(task_codes)))
    )
    demands: List[TrafficDemand] = list(
        db.scalars(select(TrafficDemand).where(TrafficDemand.task_code.in_(task_codes)))
    )
    demands_by_task: Dict[str, List[TrafficDemand]] = {}
    for d in demands:
        demands_by_task.setdefault(d.task_code, []).append(d)

    out: List[Tuple[CommTask, List[TrafficDemand]]] = []
    for t in tasks:
        out.append((t, demands_by_task.get(t.task_code, [])))
    return out


def _has_pending_capacity_alarm(db: Session, link_code: str) -> bool:
    """幂等检查：同一链路是否已存在未处理的「容量超限」告警。"""
    stmt = select(ResourceAlarm).where(
        ResourceAlarm.link_code == link_code,
        ResourceAlarm.alarm_type == "容量超限",
    )
    return len(list(db.scalars(stmt))) > 0


def _ensure_capacity_alarm(
    db: Session, link_code: str, now: int, predicted_min: Optional[int]
) -> Optional[ResourceAlarm]:
    """幂等写入容量超限告警，返回新写入或已存在的告警。"""
    if _has_pending_capacity_alarm(db, link_code):
        return None
    alarm = ResourceAlarm(
        alarm_code=_gen_alarm_code(),
        link_code=link_code,
        alarm_type="容量超限",
        native_severity="critical",
        event_min=now,
        predicted_min=predicted_min,
    )
    db.add(alarm)
    db.flush()
    return alarm


# ---------- 核心算法 ----------

def calc_occupancy(
    db: Session,
    link_code: str,
    as_of_min: Optional[int] = None,
) -> Dict[str, Any]:
    """计算单条链路的占用与预警状态。"""
    clock: SceneClock = get_clock()
    now = as_of_min if as_of_min is not None else clock.now_min()

    # 1. 取该链路当前承载的任务 + 全部需求
    link: Optional[CommLink] = db.get(CommLink, link_code)
    if link is None:
        raise ValueError(f"链路不存在: {link_code}")
    task_with_demands: List[Tuple[CommTask, List[TrafficDemand]]] = _load_link_tasks(
        db, link_code
    )
    tasks: List[CommTask] = [t for t, _ in task_with_demands]

    # 2. 当前占用
    current: float = 0.0
    for _t, demands in task_with_demands:
        for d in demands:
            if d.valid_from_min <= now and (
                d.valid_to_min is None or now < d.valid_to_min
            ):
                current += float(d.demand_gbps or 0)

    # 4. 前瞻窗口
    link_la: int = link.lookahead_min if link.lookahead_min else 30
    tasks_la: List[int] = [t.lookahead_min if t.lookahead_min else 30 for t in tasks]
    lookahead: int = max([link_la] + tasks_la + [30])

    # 5. 检查点集合：窗口终点 + 所有未来 valid_from_min
    checkpoints: Set[int] = {now + lookahead}
    for _t, demands in task_with_demands:
        for d in demands:
            if now < d.valid_from_min <= now + lookahead:
                checkpoints.add(d.valid_from_min)

    # 6. 逐检查点求瞬时占用 → max_predicted + future
    #    R2 语义统一：future 与 max_predicted 走同一套检查点求和。
    #    - max_predicted：未来窗口内最大瞬时占用（含窗口终点 now+lookahead）
    #    - future：未来窗口内第一个非当前检查点的瞬时占用
    #      （即 min(checkpoints) 时刻的瞬时占用，与「下一个需求变化点」对齐）
    max_predicted: float = 0.0
    predicted_min: Optional[int] = None
    future: float = 0.0
    sorted_cps: List[int] = sorted(checkpoints)
    for m_prime in sorted_cps:
        pred: float = 0.0
        for _t, demands in task_with_demands:
            for d in demands:
                if d.valid_from_min <= m_prime and (
                    d.valid_to_min is None or m_prime < d.valid_to_min
                ):
                    pred += float(d.demand_gbps or 0)
        if pred > max_predicted:
            max_predicted = pred
            predicted_min = m_prime
    # future = 第一个非 now 的检查点时刻的瞬时占用
    if sorted_cps:
        first_cp: int = sorted_cps[0]
        for d_check in task_with_demands:
            for d in d_check[1]:
                if d.valid_from_min <= first_cp and (
                    d.valid_to_min is None or first_cp < d.valid_to_min
                ):
                    future += float(d.demand_gbps or 0)

    # 7. 三级判定（严格大于）
    capacity = float(link.capacity_gbps or 0)
    warning = float(link.warning_gbps or 0)
    if current > capacity:
        warn_status = "超容量"
    elif max_predicted > capacity:
        warn_status = "超容量"
    elif future > warning:
        warn_status = "超预警线"
    else:
        warn_status = "正常"

    # 8. 回写链路字段
    previous_status: Optional[str] = link.warn_status
    link.current_load_gbps = round(current, 2)
    link.future_load_gbps = round(future, 2)
    link.warn_status = warn_status

    # 9. 超容量 → 幂等写容量超限告警
    new_alarm: Optional[ResourceAlarm] = None
    if warn_status == "超容量":
        new_alarm = _ensure_capacity_alarm(db, link_code, now, predicted_min)

    # 10. 写事件流水
    if new_alarm is not None:
        db.add(
            SceneEvent(
                event_code=f"EVT-OE-{datetime.now().strftime('%H%M%S%f')}",
                event_type="occupancy_exceeded",
                ref_type="alarm",
                ref_code=new_alarm.alarm_code,
                occur_min=now,
                summary=(
                    f"{link_code} 预测 T+{predicted_min - now if predicted_min else '?'}"
                    f" 达 {round(max_predicted, 2)}G 超容量 {capacity}G"
                ),
            )
        )
    elif previous_status != warn_status:
        db.add(
            SceneEvent(
                event_code=f"EVT-SC-{datetime.now().strftime('%H%M%S%f')}",
                event_type="state_changed",
                ref_type="link",
                ref_code=link_code,
                occur_min=now,
                summary=f"{link_code} {previous_status or '无'} -> {warn_status}",
            )
        )

    db.flush()

    # 11. ws 推送 toast（跨 loop 安全：safe_create_task）
    if warn_status in ("超预警线", "超容量"):
        if warn_status == "超预警线":
            level = "warn"
            message = (
                f"{link_code} 未来占用 {round(future, 2)}G 超预警线 {warning}G"
            )
        else:
            level = "error"
            offset = predicted_min - now if predicted_min is not None else None
            message = (
                f"{link_code} 预测T+{offset}达{round(max_predicted, 2)}G超容量{capacity}G"
            )
        from app.services.engine import safe_push

        safe_push("toast", {"level": level, "message": message})

    return {
        "link_code": link_code,
        "current_load_gbps": round(current, 2),
        "future_load_gbps": round(future, 2),
        "predicted_load_max_gbps": round(max_predicted, 2),
        "predicted_min": predicted_min,
        "warn_status": warn_status,
    }


# ---------- 全局重算 ----------

def recalc_all(db: Session, as_of_min: Optional[int] = None) -> List[Dict[str, Any]]:
    """遍历所有 oper_state='up' 的链路，逐一调用 calc_occupancy。

    对 warn_status='超容量' 的链路，若尚无「待审批」方案，自动调用 plan.generate_plans。
    """
    up_links: List[CommLink] = list(
        db.scalars(select(CommLink).where(CommLink.oper_state == "up"))
    )
    results: List[Dict[str, Any]] = []
    for l in up_links:
        r = calc_occupancy(db, l.link_code, as_of_min=as_of_min)
        results.append(r)

    # 超容量且无待审批方案 → 触发 ACT-03
    for r in results:
        if r["warn_status"] != "超容量":
            continue
        link_code: str = r["link_code"]
        # 找最近一条该链路的容量超限告警
        cap_alarm = db.scalar(
            select(ResourceAlarm)
            .where(
                ResourceAlarm.link_code == link_code,
                ResourceAlarm.alarm_type == "容量超限",
            )
            .order_by(ResourceAlarm.event_min.desc())
            .limit(1)
        )
        if cap_alarm is None:
            continue
        # 边界6：以 alarm_code 维度做幂等检查。
        # 不同告警（哪怕同链路）即使都触发容量超限，也应各自生成方案。
        # generate_plans_for_alarm 内部已按 alarm_code+status='待审批' 幂等，
        # 这里再防御一遍，避免新告警被旧告警的待审批方案「吃掉」。
        pending = list(
            db.scalars(
                select(CommPlan).where(
                    CommPlan.alarm_code == cap_alarm.alarm_code,
                    CommPlan.status == "待审批",
                )
            )
        )

        # 边界8：预测超限点距当前不足 60 秒（V4.1 1:1 → 1 场景分钟），
        # 走 R3 硬约束：作废旧方案并立即重生一组新方案。
        now = as_of_min if as_of_min is not None else get_clock().now_min()
        predicted_min = r.get("predicted_min")
        imminent: bool = (
            predicted_min is not None and (predicted_min - now) <= 1
        )
        if pending and not imminent:
            continue
        if pending and imminent:
            # 把旧待审批方案作废，避免新弹窗与旧弹窗并存
            for p in pending:
                p.status = "已作废"
            # 取消该告警组的倒计时（人类决策不再有意义）
            try:
                from app.services.approval import _cancel_countdown

                _cancel_countdown(cap_alarm.alarm_code)
            except Exception:
                pass
        # 局部 import 避免循环依赖
        from app.services.plan import generate_plans_for_alarm

        generate_plans_for_alarm(db, cap_alarm.alarm_code)

    db.flush()
    return results


# ---------- 兼容旧接口 ----------

def update_link_loads(db: Session) -> None:
    """兼容旧调用：等价于 recalc_all。"""
    recalc_all(db)
