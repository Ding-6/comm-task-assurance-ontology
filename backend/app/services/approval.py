"""ACT-04 人工审批决策 + 60 秒超时自动执行。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.database import SessionLocal
from app.core.scene_clock import SceneClock, get_clock
from app.models.approval import ApprovalRecord
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.plan import CommPlan
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding
from app.services.occupancy import recalc_all
from app.services.repair import request_repair


# ---------- 全局并发保护 + 倒计时任务簿 ----------

_DECIDE_LOCK: asyncio.Lock = asyncio.Lock()
_COUNTDOWN_LOCK: asyncio.Lock = asyncio.Lock()
_COUNTDOWN_TASKS: Dict[str, asyncio.Task[None]] = {}
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _set_main_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """记录进程级事件循环，供跨线程的同步取消入口使用。"""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    loop = _MAIN_LOOP
    if loop is not None and loop.is_closed():
        return None
    return loop


async def _pop_countdown_locked(alarm_code: str) -> Optional[asyncio.Task[None]]:
    """在 _COUNTDOWN_LOCK 保护下弹出任务簿条目。"""
    async with _COUNTDOWN_LOCK:
        return _COUNTDOWN_TASKS.pop(alarm_code, None)


async def _set_countdown_locked(alarm_code: str, task: asyncio.Task[None]) -> None:
    """在 _COUNTDOWN_LOCK 保护下写入任务簿条目。"""
    async with _COUNTDOWN_LOCK:
        _COUNTDOWN_TASKS[alarm_code] = task


def _next_approval_seq(db: Session, plan_code: str) -> int:
    """APV-{plan_code}-{seq}，seq 递增。"""
    prefix = f"APV-{plan_code}-"
    rows = list(
        db.scalars(
            select(ApprovalRecord).where(ApprovalRecord.approval_code.like(f"{prefix}%"))
        )
    )
    return len(rows) + 1


def _cancel_countdown(alarm_code: str) -> None:
    """取消指定告警组的 60 秒倒计时任务（同步入口，best-effort）。

    真要等任务退出请用 await _cancel_countdown_async。
    从同步上下文（HTTP 路由 / occupancy 回调）调用时，会把异步取消
    派发到运行中的事件循环，避免跨线程直接触碰 asyncio.Lock。
    """
    async def _do_cancel() -> None:
        task = await _pop_countdown_locked(alarm_code)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _get_main_loop()

    if loop is None or loop.is_closed():
        return

    # 跨线程安全：run_coroutine_threadsafe 在同 loop 下也可用。
    future = asyncio.run_coroutine_threadsafe(_do_cancel(), loop)
    try:
        future.result(timeout=0)
    except Exception:
        # best-effort，不阻塞调用方
        pass


async def _cancel_countdown_async(alarm_code: str) -> None:
    """异步版：真正等待 cancel 生效。"""
    task = await _pop_countdown_locked(alarm_code)
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# ---------- 核心：decide ----------

async def decide(
    db: Session,
    plan_code: str,
    decision: str,
    reason: Optional[str] = None,
    approver: str = "ROLE-APPROVER",
    decision_source: str = "人工",
) -> Dict[str, Any]:
    """人工/系统审批决策（async；带 _DECIDE_LOCK + 真正等待 cancel 完成）。

    返回：
        {
            "approval_code": "APV-...",
            "plan": CommPlan,
            "executed": bool,         # reroute 批准时执行了迁移
            "canceled_countdown": bool,
        }
    """
    # 先抢锁，所有写路径（HTTP 同步入口 + 后台超时任务）都走这里
    async with _DECIDE_LOCK:
        return await _do_decide(
            db, plan_code, decision, reason, approver, decision_source
        )


async def _do_decide(
    db: Session,
    plan_code: str,
    decision: str,
    reason: Optional[str],
    approver: str,
    decision_source: str,
) -> Dict[str, Any]:
    clock: SceneClock = get_clock()
    now = clock.now_min()

    # 1. 校验方案
    plan: Optional[CommPlan] = db.get(CommPlan, plan_code)
    if plan is None:
        raise ValueError(f"方案不存在: {plan_code}")
    if plan.status != "待审批":
        raise ValueError(f"方案状态非'待审批': {plan_code} status={plan.status}")
    if plan.status == "已作废":
        raise ValueError(f"方案已作废: {plan_code}")
    if approver not in ("ROLE-APPROVER", "SYSTEM"):
        raise ValueError(f"Agent 无权审批: approver={approver}")

    alarm_code: str = plan.alarm_code

    # 2. 真正等待 cancel 生效（避免与超时任务在临界区并发）
    await _cancel_countdown_async(alarm_code)
    canceled_countdown: bool = True

    # 3. 写审批记录
    seq = _next_approval_seq(db, plan_code)
    approval_code = f"APV-{plan_code}-{seq:02d}"
    approval = ApprovalRecord(
        approval_code=approval_code,
        plan_code=plan_code,
        decision=decision,
        reason=reason,
        approver=approver,
        decision_source=decision_source,
        decided_min=now,
    )
    db.add(approval)

    # 4. 同组方案
    siblings: List[CommPlan] = list(
        db.scalars(
            select(CommPlan).where(
                CommPlan.alarm_code == alarm_code,
                CommPlan.status == "待审批",
            )
        )
    )

    executed: bool = False
    if decision == "批准":
        if plan.plan_type == "reroute":
            _execute_reroute(db, plan, now)
            plan.status = "已执行"
            executed = True
            for sib in siblings:
                if sib.plan_code != plan.plan_code:
                    sib.status = "已作废"
        elif plan.plan_type == "repair":
            plan.status = "批准"
            try:
                request_repair(db, alarm_code=alarm_code, plan_code=plan.plan_code)
            except Exception:
                pass
            for sib in siblings:
                if sib.plan_code != plan.plan_code:
                    sib.status = "已作废"
    else:
        plan.status = "拒绝"
        for sib in siblings:
            if sib.plan_code != plan.plan_code:
                sib.status = "已作废"

    # 5. 事件流水
    db.add(
        SceneEvent(
            event_code=f"EVT-APV-{datetime.now().strftime('%H%M%S%f')}",
            event_type="approval_decided",
            ref_type="approval",
            ref_code=approval_code,
            occur_min=now,
            summary=f"{plan_code} {decision} ({decision_source})",
        )
    )
    db.flush()

    # 6. 闭环
    recalc_all(db, as_of_min=now)
    db.flush()

    # 7. 从 session 重新读取最新持久化的 ApprovalRecord（与 _do_decide_sync 一致）
    approval_obj: Optional[ApprovalRecord] = db.get(ApprovalRecord, approval_code)

    # 8. ws modal_close（async 路径上可直接 await broadcast）
    await get_hub().broadcast(
        "modal_close",
        {
            "approval_code": approval_code,
            "plan_code": plan_code,
            "decision": decision,
            "decision_source": decision_source,
            "executed": executed,
        },
    )

    return {
        "approval_code": approval_code,
        "plan": plan,
        "approval": approval_obj,
        "executed": executed,
        "canceled_countdown": canceled_countdown,
    }


def decide_sync(
    db: Session,
    plan_code: str,
    decision: str,
    reason: Optional[str] = None,
    approver: str = "ROLE-APPROVER",
    decision_source: str = "人工",
) -> Dict[str, Any]:
    """同步入口：从同步路由调用时，把 async 任务投到主 loop 执行并阻塞等待。

    绝不在子线程跑 asyncio.run —— 子线程的 loop 会和主 loop 上的 ws 客户端冲突，
    死锁所有广播。
    """
    try:
        # 已处在主 loop 的 async 上下文里？直接 await
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _get_main_loop()

    if loop is None or loop.is_closed():
        # 没有任何事件循环：只能走纯同步路径
        return _do_decide_sync(db, plan_code, decision, reason, approver, decision_source)

    # 在主 loop 上调度并阻塞等结果
    future = asyncio.run_coroutine_threadsafe(
        _do_decide(db, plan_code, decision, reason, approver, decision_source),
        loop,
    )
    return future.result()


def _do_decide_sync(
    db: Session,
    plan_code: str,
    decision: str,
    reason: Optional[str],
    approver: str,
    decision_source: str,
) -> Dict[str, Any]:
    """同步版本：无 cancel 等待 + 不调 ws（用于测试 / 离线批处理）。"""
    clock: SceneClock = get_clock()
    now = clock.now_min()

    plan: Optional[CommPlan] = db.get(CommPlan, plan_code)
    if plan is None or plan.status != "待审批":
        raise ValueError("方案不存在或状态非待审批")
    if approver not in ("ROLE-APPROVER", "SYSTEM"):
        raise ValueError("Agent 无权审批")

    _cancel_countdown(plan.alarm_code)

    seq = _next_approval_seq(db, plan_code)
    approval_code = f"APV-{plan_code}-{seq:02d}"
    db.add(
        ApprovalRecord(
            approval_code=approval_code,
            plan_code=plan_code,
            decision=decision,
            reason=reason,
            approver=approver,
            decision_source=decision_source,
            decided_min=now,
        )
    )

    executed = False
    if decision == "批准":
        if plan.plan_type == "reroute":
            _execute_reroute(db, plan, now)
            plan.status = "已执行"
            executed = True
        elif plan.plan_type == "repair":
            plan.status = "批准"
            try:
                request_repair(db, alarm_code=plan.alarm_code, plan_code=plan.plan_code)
            except Exception:
                pass
    else:
        plan.status = "拒绝"

    # 同组作废
    siblings = list(
        db.scalars(
            select(CommPlan).where(
                CommPlan.alarm_code == plan.alarm_code,
                CommPlan.status == "待审批",
                CommPlan.plan_code != plan_code,
            )
        )
    )
    for sib in siblings:
        sib.status = "已作废"

    db.add(
        SceneEvent(
            event_code=f"EVT-APV-{datetime.now().strftime('%H%M%S%f')}",
            event_type="approval_decided",
            ref_type="approval",
            ref_code=approval_code,
            occur_min=now,
            summary=f"{plan_code} {decision} ({decision_source})",
        )
    )
    db.flush()
    recalc_all(db, as_of_min=now)
    db.flush()

    # 从 session 重新读取最新持久化的 ApprovalRecord，确保返回对象的所有字段
    # （decision / approver / decision_source / decided_min）都是 DB 实际写入值。
    approval_obj: Optional[ApprovalRecord] = db.get(ApprovalRecord, approval_code)

    return {
        "approval_code": approval_code,
        "plan": plan,
        "approval": approval_obj,
        "executed": executed,
        "canceled_countdown": True,
    }


async def decide_async(
    db: Session,
    plan_code: str,
    decision: str,
    reason: Optional[str] = None,
    approver: str = "ROLE-APPROVER",
    decision_source: str = "人工",
) -> Dict[str, Any]:
    """兼容旧名：直接转调 decide（已经是 async + 加锁）。"""
    return await decide(
        db,
        plan_code=plan_code,
        decision=decision,
        reason=reason,
        approver=approver,
        decision_source=decision_source,
    )


# ---------- 执行 reroute 的内部方法 ----------

def _execute_reroute(db: Session, plan: CommPlan, now: int) -> None:
    """reroute 方案被批准时执行：把故障链路上承载的任务迁到 target_link_code。"""
    fault_code: str = plan.link_code
    target_code: Optional[str] = plan.target_link_code
    if not target_code:
        raise ValueError(f"reroute 方案无 target_link_code: {plan.plan_code}")

    target: Optional[CommLink] = db.get(CommLink, target_code)
    if target is None:
        raise ValueError(f"目标链路不存在: {target_code}")
    target.oper_state = "up"  # 备用启用

    # 故障链路上当前承载的任务
    rows: List[TaskLinkBinding] = list(
        db.scalars(
            select(TaskLinkBinding)
            .where(TaskLinkBinding.link_code == fault_code)
            .order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
        )
    )
    latest: Dict[str, TaskLinkBinding] = {}
    for r in rows:
        latest.setdefault(r.task_code, r)

    for b in latest.values():
        db.add(
            TaskLinkBinding(
                task_code=b.task_code,
                link_code=target_code,
                assigned_min=now,
                note=f"{fault_code} 批准转备用，由 {now} 执行",
            )
        )
        task: Optional[CommTask] = db.get(CommTask, b.task_code)
        if task is not None:
            task.current_link_code = target_code


# ---------- 倒计时 ----------

def start_countdown(alarm_code: str, plan_group_id: str, timeout_sec: int = 60) -> None:
    """启动 60 秒倒计时；超时自动执行 is_default='是' 的方案。

    plan_group_id 当前未使用，预留多组批次的扩展位。
    """
    # 若已存在旧任务，先取消
    _cancel_countdown(alarm_code)

    async def _runner() -> None:
        try:
            await asyncio.sleep(timeout_sec)
        except asyncio.CancelledError:
            return

        # 到了时间点：用一个新 session 查是否还有待审批方案
        from app.core.database import SessionLocal as _SL

        s: Session = _SL()
        try:
            still_pending: List[CommPlan] = list(
                s.scalars(
                    select(CommPlan).where(
                        CommPlan.alarm_code == alarm_code,
                        CommPlan.status == "待审批",
                    )
                )
            )
            if not still_pending:
                return

            # 找 is_default='是' 的方案
            default_plan: Optional[CommPlan] = next(
                (p for p in still_pending if p.is_default == "是"), None
            )
            if default_plan is None:
                # 没默认方案就放弃（避免误执行）
                return

            async with _DECIDE_LOCK:
                await decide(
                    s,
                    plan_code=default_plan.plan_code,
                    decision="批准",
                    reason="60 秒未决策，自动执行保守默认方案",
                    approver="SYSTEM",
                    decision_source="超时自动",
                )
                s.commit()
        except asyncio.CancelledError:
            return
        except Exception:
            # 静默吞掉异常，避免后台任务崩溃传播
            try:
                s.rollback()
            except Exception:
                pass
        finally:
            s.close()
            # 仅清理仍指向本任务的条目，避免覆盖已被新倒计时替换的 entry
            async def _cleanup() -> None:
                async with _COUNTDOWN_LOCK:
                    if _COUNTDOWN_TASKS.get(alarm_code) is task:
                        _COUNTDOWN_TASKS.pop(alarm_code, None)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_cleanup())
            except RuntimeError:
                # loop 已关：best-effort 同步清理
                _COUNTDOWN_TASKS.pop(alarm_code, None)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_runner())
        # 记录主 loop，供跨线程同步取消使用
        _set_main_loop(loop)
        _register_countdown_sync(alarm_code, task)
    except RuntimeError:
        # 没有运行中的事件循环，跳过
        pass


def _register_countdown_sync(alarm_code: str, task: asyncio.Task[None]) -> None:
    """在已有事件循环的同步上下文里把 _COUNTDOWN_TASKS 写入安全化。

    start_countdown 通常从 FastAPI 同步路由（外层事件循环正在跑）调用，
    这里通过 run_coroutine_threadsafe 派发真正的加锁写。
    """
    async def _do_set() -> None:
        await _set_countdown_locked(alarm_code, task)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = _get_main_loop()

    if loop is None or loop.is_closed():
        _COUNTDOWN_TASKS[alarm_code] = task  # 兜底
        return

    future = asyncio.run_coroutine_threadsafe(_do_set(), loop)
    try:
        future.result(timeout=0)
    except Exception:
        _COUNTDOWN_TASKS[alarm_code] = task


# ---------- 兼容旧接口 ----------

def decide_approval(
    db: Session,
    approval_code: str,
    decision: str,
    approver: str,
    decision_source: str,
    reason: Optional[str] = None,
) -> ApprovalRecord:
    """兼容旧调用：通过 approval_code 找到 plan_code，再调 decide。

    返回真正从 session 读出来的 ApprovalRecord（带 DB 持久化的所有字段），
    不再 new 一个空对象。
    """
    ap: Optional[ApprovalRecord] = db.get(ApprovalRecord, approval_code)
    plan_code: Optional[str] = ap.plan_code if (ap is not None and ap.plan_code) else None

    if plan_code is None and approval_code.startswith("APV-"):
        plan_code = approval_code[len("APV-"):]

    if plan_code is None:
        raise ValueError(f"审批单无关联方案: {approval_code}")

    # 同步入口：HTTP/单元测试场景用 decide_sync，加锁 + 不阻塞 cancel
    result = decide_sync(
        db,
        plan_code=plan_code,
        decision=decision,
        reason=reason,
        approver=approver,
        decision_source=decision_source,
    )

    approval_obj: Optional[ApprovalRecord] = result.get("approval")
    if approval_obj is None:
        # 兜底：即使 _do_decide_sync 出了异常也保证返回的对象字段真实可读
        raise ValueError("审批写入失败：未读到持久化记录")
    return approval_obj


async def schedule_auto_timeout(approval_code: str, timeout_sec: int = 60) -> None:
    """兼容旧调用：从 approval_code 拿 alarm_code，转 start_countdown。"""
    from app.core.database import SessionLocal as _SL

    s: Session = _SL()
    try:
        ap: Optional[ApprovalRecord] = s.get(ApprovalRecord, approval_code)
        if ap is None or not ap.plan_code:
            return
        plan: Optional[CommPlan] = s.get(CommPlan, ap.plan_code)
        if plan is None:
            return
        start_countdown(plan.alarm_code, approval_code, timeout_sec=timeout_sec)
    finally:
        s.close()
