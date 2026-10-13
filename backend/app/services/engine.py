"""场景引擎：启动 / tick 推进 / 预订事件兑现 / 输入分发。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.ws import get_hub
from app.core.database import SessionLocal
from app.core.scene_clock import SceneClock, get_clock
from app.models.alarm import ResourceAlarm
from app.models.approval import ApprovalRecord
from app.models.demand import TrafficDemand
from app.models.event import SceneEvent
from app.models.link import CommLink
from app.models.plan import CommPlan
from app.models.repair_order import RepairOrder
from app.models.task import CommTask
from app.models.task_link import TaskLinkBinding
from app.services.intent import parse_input
from app.services.occupancy import calc_occupancy, recalc_all
from app.services.plan import generate_plans_for_alarm
from app.services.switch import handle_link_down


# =====================================================================
# 引擎全局状态
# =====================================================================

# tick 周期：60 真实秒 = 1 场景分钟（V4.1 固定 1 倍速）
_TICK_SECONDS: float = 60.0
_LAST_TICK_AT: Optional[datetime] = None
_LOOP_TASK: Optional[asyncio.Future[None]] = None
_LOOP_STOP: Optional[asyncio.Event] = None
# 已被 tick 兑现过的 event_code，避免重复处理
_CONSUMED_EVENTS: set[str] = set()
# 主 event loop 引用（由 lifespan 注入）。所有跨线程 ws 推送都通过它
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """由 main.py lifespan 调用，注册主 loop 引用。"""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """获取主 loop 引用（供其他 service 用）。"""
    return _MAIN_LOOP


def safe_push(message_type: str, payload: Any = None) -> None:
    """跨线程安全地把 ws 消息投递到主 event loop。

    在同步路由（线程池）或后台任务里调用时，不会触发 RuntimeError，
    也不会在错的 loop 上 await send_text 死锁 ws 客户端。
    """
    if _MAIN_LOOP is None or _MAIN_LOOP.is_closed():
        return
    try:
        coro = get_hub().broadcast(message_type, payload)
        asyncio.run_coroutine_threadsafe(coro, _MAIN_LOOP)
    except Exception:
        # 静默丢弃，避免在热路径上抛错
        pass


def safe_create_task(coro_factory) -> None:
    """从任意线程安全地把协程投递到主 loop 启动。

    coro_factory 是「无参 callable，返回 coroutine」的工厂；必须无参，因为
    run_coroutine_threadsafe 不接受 coroutine 之外的参数。
    """
    if _MAIN_LOOP is None or _MAIN_LOOP.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(coro_factory(), _MAIN_LOOP)
    except Exception:
        pass


# =====================================================================
# tick 实现
# =====================================================================

async def _tick_once() -> None:
    """单次 tick：扫描待兑现预订、刷新占用、推 state。"""
    global _LAST_TICK_AT
    clock: SceneClock = get_clock()
    if not clock.is_running() or clock.is_paused:
        return

    now_min = clock.now_min()
    _LAST_TICK_AT = datetime.now()

    db: Session = SessionLocal()
    try:
        # 1. 扫描预订事件（occur_min <= now 且未兑现）
        stmt = (
            select(SceneEvent)
            .where(
                SceneEvent.event_type == "task_booked",
                SceneEvent.occur_min <= now_min,
            )
            .order_by(SceneEvent.occur_min)
        )
        events: List[SceneEvent] = list(db.scalars(stmt))

        for ev in events:
            if ev.event_code in _CONSUMED_EVENTS:
                continue
            await _dispatch_booking(db, ev)
            _CONSUMED_EVENTS.add(ev.event_code)
            # 保留原 task_booked 行的 event_type（便于审计追溯"这条原本是预订"），
            # 仅在 summary 末尾追加「 | 已兑现@T+XX」。
            ev.summary = (ev.summary or "") + f" | 已兑现@T+{now_min}"
            # 新增一条兑现动作流水，把"兑现"这一动作作为独立事件记下来，
            # 让事件链 alarm_injected → state_changed(兑现) → switch_done → …
            # 保持完整。
            db.add(
                SceneEvent(
                    event_code=f"EVT-RED-{datetime.now().strftime('%H%M%S%f')}",
                    event_type="state_changed",
                    ref_type=ev.ref_type,
                    ref_code=ev.ref_code,
                    occur_min=now_min,
                    summary=f"预订事件兑现：{ev.summary}",
                )
            )

        # 2. 全链路前瞻扫描
        recalc_all(db, as_of_min=now_min)

        # 3. 写当前 state 快照
        snap = get_state(db)
        db.commit()
    finally:
        db.close()

    # 4. 推 state 给所有 ws 客户端
    await get_hub().broadcast("state", snap)


async def _dispatch_booking(db: Session, ev: SceneEvent) -> None:
    """兑现一个预订事件。"""
    if ev.ref_type == "alarm" and ev.ref_code:
        # EVT-0001 形式：ref_code 是 link_code
        link: Optional[CommLink] = db.get(CommLink, ev.ref_code)
        if link is None:
            return
        # 注入 link_down 告警
        seq = len(list(db.scalars(select(ResourceAlarm)))) + 1
        alarm = ResourceAlarm(
            alarm_code=f"AL-{seq:02d}",
            link_code=link.link_code,
            alarm_type="link_down",
            native_severity="critical",
            event_min=ev.occur_min,
        )
        db.add(alarm)
        db.flush()
        # 补 alarm_injected 事件流水（与 SK-01 /api/comm/alarm 路由一致），
        # 形成 alarm_injected → switch_done → occupancy_exceeded → plan_generated
        # → approval_decided → link_restored 闭环证据链。
        db.add(
            SceneEvent(
                event_code=f"EVT-AI-{datetime.now().strftime('%H%M%S%f')}",
                event_type="alarm_injected",
                ref_type="alarm",
                ref_code=alarm.alarm_code,
                occur_min=ev.occur_min,
                summary=f"{alarm.alarm_code} link_down @ {link.link_code}",
            )
        )
        # ACT-01 切换
        handle_link_down(db, link.link_code, as_of_min=ev.occur_min)
        # ACT-03 方案
        generate_plans_for_alarm(db, alarm.alarm_code)
        # 推 alert 给前端
        await get_hub().broadcast(
            "alert",
            {
                "type": "alarm_injected",
                "alarm_code": alarm.alarm_code,
                "link_code": link.link_code,
                "occur_min": ev.occur_min,
            },
        )

    elif ev.ref_type == "demand" and ev.ref_code:
        # EVT-0002 形式：ref_code = D-{task}-N 需求码
        # summary 里编码：task=<T-X>;gbps=<float>;<人类可读描述>
        code: str = ev.ref_code
        existing: Optional[TrafficDemand] = db.get(TrafficDemand, code)
        if existing is not None:
            return
        # 解析 summary
        task_code: str = "T-B"
        gbps: float = 6.00
        if ev.summary:
            for part in ev.summary.split(";"):
                kv = part.split("=", 1)
                if len(kv) != 2:
                    continue
                k, v = kv[0].strip(), kv[1].strip()
                if k == "task":
                    task_code = v
                elif k == "gbps":
                    try:
                        gbps = float(v)
                    except ValueError:
                        pass
        db.add(
            TrafficDemand(
                demand_code=code,
                task_code=task_code,
                valid_from_min=ev.occur_min,
                demand_gbps=gbps,
                valid_to_min=None,
            )
        )
        # 推 alert
        await get_hub().broadcast(
            "alert",
            {
                "type": "demand_added",
                "demand_code": code,
                "task_code": task_code,
                "demand_gbps": gbps,
                "occur_min": ev.occur_min,
            },
        )


# =====================================================================
# 后台主循环
# =====================================================================

async def _engine_loop() -> None:
    """每 _TICK_SECONDS 真实秒触发一次 tick。"""
    while True:
        try:
            await _tick_once()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            try:
                await get_hub().broadcast("engine_error", {"error": str(exc)})
            except Exception:
                pass
        await asyncio.sleep(_TICK_SECONDS)


def _ensure_loop() -> None:
    """确保后台 tick 循环在跑。

    必须在 main loop 上调度（从同步路由里调时不能 asyncio.get_running_loop），
    优先用 lifespan 注册的 _MAIN_LOOP；未注册则放弃（lifespan 启动后再调用即可）。
    """
    global _LOOP_TASK
    if _LOOP_TASK is not None and not _LOOP_TASK.done():
        return
    if _MAIN_LOOP is None or _MAIN_LOOP.is_closed():
        return
    _LOOP_TASK = asyncio.run_coroutine_threadsafe(_engine_loop(), _MAIN_LOOP)


def _stop_loop() -> None:
    """停止后台 tick 循环。"""
    global _LOOP_TASK
    if _LOOP_TASK is not None and not _LOOP_TASK.done():
        _LOOP_TASK.cancel()
    _LOOP_TASK = None


# =====================================================================
# 引擎控制：start / pause / resume / reset
# =====================================================================

def start_scene() -> Dict[str, Any]:
    """启动场景。"""
    clock = get_clock()
    clock.start()
    _CONSUMED_EVENTS.clear()
    _ensure_loop()

    db = SessionLocal()
    try:
        snap = get_state(db)
    finally:
        db.close()

    # 异步推送初始 state（跨 loop 安全）
    safe_push("state", snap)

    return snap


def pause_scene() -> Dict[str, Any]:
    """暂停 tick 扫描（业务时钟继续走）。"""
    clock = get_clock()
    clock.pause()
    db = SessionLocal()
    try:
        snap = get_state(db)
    finally:
        db.close()
    return snap


def resume_scene() -> Dict[str, Any]:
    """恢复 tick 扫描。"""
    clock = get_clock()
    clock.resume()
    _ensure_loop()
    db = SessionLocal()
    try:
        snap = get_state(db)
    finally:
        db.close()
    return snap


def reset_scene() -> Dict[str, Any]:
    """复位：停止循环 + 重置时钟 + 清空已兑现缓存 + 重置业务数据为初始状态。

    按依赖顺序：events → approvals → plans → repair_orders → alarms →
    task_links → demands → tasks → links，避开外键约束。
    """
    global _LAST_TICK_AT
    _stop_loop()
    clock = get_clock()
    clock.reset()
    _CONSUMED_EVENTS.clear()
    _LAST_TICK_AT = None

    db = SessionLocal()
    try:
        _reset_default_scene(db)
        snap = get_state(db)
    finally:
        db.close()
    return snap


def _reset_default_scene(db: Session) -> None:
    """仅复位业务数据（链路/任务/需求/归属/预订事件），不动时钟与后台循环。

    给 POST /api/comm/reset 业务路由复用；POST /api/scene/reset 由 reset_scene() 调用。
    """
    from app.models.approval import ApprovalRecord
    from app.models.plan import CommPlan
    from app.models.repair_order import RepairOrder
    from app.models.alarm import ResourceAlarm
    from app.models.event import SceneEvent
    from app.models.task_link import TaskLinkBinding
    from app.models.demand import TrafficDemand
    from app.models.task import CommTask
    from app.models.link import CommLink

    # 按依赖反序清空
    for cls in (
        ApprovalRecord,
        CommPlan,
        RepairOrder,
        ResourceAlarm,
        SceneEvent,
        TaskLinkBinding,
        TrafficDemand,
        CommTask,
        CommLink,
    ):
        db.query(cls).delete()
        db.flush()

    # 重插初始数据（与 建表脚本.sql 保持一致）
    db.add_all(
        [
            CommLink(
                link_code="L-1H",
                link_name="指挥通信主用电路",
                capacity_gbps=10.00,
                warning_gbps=8.00,
                oper_state="up",
                avg_repair_min=30,
                lookahead_min=30,
                backup_link_code="L-3H",
                current_load_gbps=0.00,
                future_load_gbps=0.00,
                warn_status="正常",
            ),
            CommLink(
                link_code="L-2H",
                link_name="直播与既有共享电路",
                capacity_gbps=10.00,
                warning_gbps=8.00,
                oper_state="up",
                avg_repair_min=30,
                lookahead_min=30,
                backup_link_code=None,
                current_load_gbps=0.00,
                future_load_gbps=0.00,
                warn_status="正常",
            ),
            CommLink(
                link_code="L-3H",
                link_name="指挥通信备用电路",
                capacity_gbps=10.00,
                warning_gbps=8.00,
                oper_state="up",
                avg_repair_min=30,
                lookahead_min=30,
                backup_link_code=None,
                current_load_gbps=0.00,
                future_load_gbps=0.00,
                warn_status="正常",
            ),
        ]
    )
    db.flush()

    db.add_all(
        [
            CommTask(
                task_code="T-A",
                task_name="指挥通信保障",
                duration_min=120,
                critical_min=None,
                owner_role="ROLE-DUTY",
                current_link_code="L-1H",
                initial_demand_gbps=3.00,
                lookahead_min=30,
            ),
            CommTask(
                task_code="T-B",
                task_name="直播传输保障",
                duration_min=120,
                critical_min=50,
                owner_role="ROLE-B",
                current_link_code="L-2H",
                initial_demand_gbps=4.00,
                lookahead_min=30,
            ),
            CommTask(
                task_code="T-C",
                task_name="既有传输保障",
                duration_min=120,
                critical_min=None,
                owner_role="ROLE-DUTY",
                current_link_code="L-2H",
                initial_demand_gbps=2.00,
                lookahead_min=30,
            ),
        ]
    )
    db.flush()

    db.add_all(
        [
            TrafficDemand(
                demand_code="D-A", task_code="T-A",
                valid_from_min=0, demand_gbps=3.00, valid_to_min=None,
            ),
            TrafficDemand(
                demand_code="D-B1", task_code="T-B",
                valid_from_min=0, demand_gbps=4.00, valid_to_min=50,
            ),
            TrafficDemand(
                demand_code="D-C", task_code="T-C",
                valid_from_min=0, demand_gbps=2.00, valid_to_min=None,
            ),
        ]
    )
    db.flush()

    db.add_all(
        [
            TaskLinkBinding(task_code="T-A", link_code="L-1H", assigned_min=0, note="场景初始归属"),
            TaskLinkBinding(task_code="T-B", link_code="L-2H", assigned_min=0, note="场景初始归属"),
            TaskLinkBinding(task_code="T-C", link_code="L-2H", assigned_min=0, note="场景初始归属"),
        ]
    )
    db.flush()

    db.add_all(
        [
            SceneEvent(
                event_code="EVT-0001",
                event_type="task_booked",
                ref_type="alarm",
                ref_code="L-1H",
                occur_min=15,
                summary="15分钟后线路1故障，预订为T+15兑现",
            ),
            SceneEvent(
                event_code="EVT-0002",
                event_type="task_booked",
                ref_type="demand",
                ref_code="D-B2",
                occur_min=50,
                summary="task=T-B;gbps=6.00;50分钟后直播需求到6.00G",
            ),
        ]
    )
    db.flush()


# =====================================================================
# 状态快照
# =====================================================================

def get_state(db: Optional[Session] = None) -> Dict[str, Any]:
    """聚合完整状态快照。"""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        clock = get_clock()
        now_min: int = clock.now_min()
        # 1. wallclock 精确到秒：start_wallclock + now_min 分钟
        wallclock: Optional[str] = None
        if clock.start_wallclock is not None:
            wc: datetime = clock.start_wallclock + timedelta(minutes=now_min)
            wallclock = wc.strftime("%H:%M:%S")

        # 2. 链路：增加 is_backup / active_repair_order
        links: List[CommLink] = list(db.scalars(select(CommLink)))
        # 反查"哪些链路的 backup_link_code == 本链路"
        backup_owners_codes: Set[str] = {
            row[0]
            for row in db.execute(
                select(CommLink.backup_link_code).where(
                    CommLink.backup_link_code.is_not(None)
                )
            ).all()
        }
        # 反查每条链路的活跃修理单（status != '已完成'）
        active_repairs: Dict[str, RepairOrder] = {}
        for o in db.scalars(
            select(RepairOrder)
            .where(RepairOrder.status != "已完成")
            .order_by(RepairOrder.request_min.desc(), RepairOrder.order_code.desc())
        ):
            if o.link_code not in active_repairs:
                active_repairs[o.link_code] = o

        link_dicts: List[Dict[str, Any]] = []
        for l in links:
            item: Dict[str, Any] = {
                "link_code": l.link_code,
                "link_name": l.link_name,
                "oper_state": l.oper_state,
                "capacity_gbps": float(l.capacity_gbps or 0),
                "warning_gbps": float(l.warning_gbps or 0),
                "current_load_gbps": float(l.current_load_gbps or 0),
                "future_load_gbps": float(l.future_load_gbps or 0),
                "warn_status": l.warn_status,
                "backup_link_code": l.backup_link_code,
                "is_backup": l.link_code in backup_owners_codes,
            }
            ro = active_repairs.get(l.link_code)
            if ro is not None:
                item["active_repair_order"] = {
                    "order_code": ro.order_code,
                    "status": ro.status or "",
                }
            else:
                item["active_repair_order"] = None
            link_dicts.append(item)

        # 3. 任务：增加 last_note / current_demand_gbps
        tasks: List[CommTask] = list(db.scalars(select(CommTask)))
        # 任务 -> 最新一条 TaskLinkBinding（assigned_min + id 倒序）
        latest_binding_by_task: Dict[str, TaskLinkBinding] = {}
        for b in db.scalars(
            select(TaskLinkBinding).order_by(
                TaskLinkBinding.task_code.asc(),
                TaskLinkBinding.assigned_min.desc(),
                TaskLinkBinding.id.desc(),
            )
        ):
            latest_binding_by_task.setdefault(b.task_code, b)
        # 任务 -> 全部 demand
        all_demands: List[TrafficDemand] = list(db.scalars(select(TrafficDemand)))
        demands_by_task: Dict[str, List[TrafficDemand]] = {}
        for d in all_demands:
            demands_by_task.setdefault(d.task_code, []).append(d)

        def _current_demand_gbps(task_code: str) -> float:
            total: float = 0.0
            for d in demands_by_task.get(task_code, []):
                if d.valid_from_min <= now_min and (
                    d.valid_to_min is None or now_min < d.valid_to_min
                ):
                    total += float(d.demand_gbps or 0)
            return round(total, 2)

        task_dicts: List[Dict[str, Any]] = []
        for t in tasks:
            lb = latest_binding_by_task.get(t.task_code)
            task_dicts.append(
                {
                    "task_code": t.task_code,
                    "task_name": t.task_name,
                    "duration_min": t.duration_min,
                    "critical_min": t.critical_min,
                    "owner_role": t.owner_role,
                    "current_link_code": t.current_link_code,
                    "initial_demand_gbps": float(t.initial_demand_gbps or 0),
                    "current_demand_gbps": _current_demand_gbps(t.task_code),
                    "lookahead_min": t.lookahead_min,
                    "last_note": lb.note if lb is not None else None,
                }
            )

        # 待审批方案
        plans: List[CommPlan] = list(
            db.scalars(select(CommPlan).where(CommPlan.status == "待审批"))
        )
        plan_dicts: List[Dict[str, Any]] = [
            {
                "plan_code": p.plan_code,
                "alarm_code": p.alarm_code,
                "plan_type": p.plan_type,
                "link_code": p.link_code,
                "target_link_code": p.target_link_code,
                "is_default": p.is_default,
                "can_meet_critical": p.can_meet_critical,
                "predicted_load_after_gbps": float(p.predicted_load_after_gbps or 0),
                "status": p.status,
                "recommendation": p.recommendation,
                "generated_min": p.generated_min,
            }
            for p in plans
        ]

        # 最近 20 条事件
        events: List[SceneEvent] = list(
            db.scalars(select(SceneEvent).order_by(SceneEvent.occur_min.desc()).limit(20))
        )
        event_dicts: List[Dict[str, Any]] = [
            {
                "event_code": e.event_code,
                "event_type": e.event_type,
                "ref_type": e.ref_type,
                "ref_code": e.ref_code,
                "occur_min": e.occur_min,
                "summary": e.summary,
            }
            for e in events
        ]

        # 链路承载映射
        bindings: List[TaskLinkBinding] = list(
            db.scalars(
                select(TaskLinkBinding).order_by(TaskLinkBinding.assigned_min.desc(), TaskLinkBinding.id.desc())
            )
        )
        carrier: Dict[str, str] = {}
        for b in bindings:
            carrier.setdefault(b.task_code, b.link_code)

        # 4. 预订事件队列：event_type=task_booked 且 occur_min > now 且未兑现
        #    「未兑现」= event_type 还没被 tick 改成 'state_changed'
        booked_events: List[Dict[str, Any]] = []
        for be in db.scalars(
            select(SceneEvent)
            .where(
                SceneEvent.event_type == "task_booked",
                SceneEvent.occur_min > now_min,
            )
            .order_by(SceneEvent.occur_min.asc())
        ):
            booked_events.append(
                {
                    "occur_min": int(be.occur_min),
                    "summary": be.summary or "",
                    "remain_min": int(be.occur_min) - now_min,
                }
            )

        return {
            "running": clock.is_running(),
            "is_paused": clock.is_paused,
            "now_min": now_min,
            "wallclock": wallclock,
            "tick_seconds": _TICK_SECONDS,
            "links": link_dicts,
            "tasks": task_dicts,
            "task_carrier": carrier,
            "pending_approvals": plan_dicts,
            "events": event_dicts,
            "booked_events": booked_events,
        }
    finally:
        if own_session:
            db.close()


# =====================================================================
# 输入分发
# =====================================================================

def handle_input(
    db: Session, category: str, payload: Any
) -> Dict[str, Any]:
    """输入框统一入口。

    category:
        - 'task'  → SK-08 添加任务（payload 必须是 dict）
        - 'link'  → SK-09 添加链路（payload 必须是 dict）
        - 'alarm' → intent.parse_input(payload) → SK-06
        - 'notice'→ intent.parse_input(payload) → SK-10/SK-07/SK-05
    """
    if category == "task":
        return _add_task(db, payload)
    if category == "link":
        return _add_link(db, payload)
    if category in ("alarm", "notice"):
        return _dispatch_parsed(db, parse_input(str(payload)))
    raise ValueError(f"未知 category: {category}")


def _add_task(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """SK-08 添加任务 + 首条需求。"""
    code: str = payload.get("task_code") or payload.get("code") or ""
    if not code:
        raise ValueError("缺少 task_code")

    # 已存在则幂等返回
    existing: Optional[CommTask] = db.get(CommTask, code)
    if existing is not None:
        return {"task_code": code, "demand_code": None, "existed": True}

    task = CommTask(
        task_code=code,
        task_name=payload.get("task_name") or payload.get("name") or code,
        duration_min=int(payload.get("duration_min", 120)),
        critical_min=payload.get("critical_min"),
        owner_role=payload.get("owner_role"),
        current_link_code=payload.get("link_code"),
        initial_demand_gbps=payload.get("demand_gbps", 0),
        lookahead_min=payload.get("lookahead_min", 30),
    )
    db.add(task)

    # 首条需求：用 D-NEW-{seq:03d} 序列保证主键唯一；valid_to_min=None
    # 表示「持续有效」（新增任务本就没有显式结束边界，符合说明书 §5.5 登记语义）。
    seq = len(list(db.scalars(select(TrafficDemand)))) + 1
    demand_code = f"D-NEW-{seq:03d}"
    db.add(
        TrafficDemand(
            demand_code=demand_code,
            task_code=code,
            valid_from_min=get_clock().now_min(),
            demand_gbps=payload.get("demand_gbps", 0),
            valid_to_min=None,
        )
    )
    # 任务归属
    if payload.get("link_code"):
        db.add(
            TaskLinkBinding(
                task_code=code,
                link_code=payload["link_code"],
                assigned_min=get_clock().now_min(),
                note="任务登记初始归属",
            )
        )
    db.flush()
    # R7：新增对象登记后触发 ACT-02 全局重算
    recalc_all(db, as_of_min=get_clock().now_min())
    return {
        "task_code": code,
        "demand_code": demand_code,
        "triggered_action": "ACT-02",
    }


def _add_link(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """SK-09 添加链路。"""
    code: str = payload.get("link_code") or payload.get("code") or ""
    if not code:
        raise ValueError("缺少 link_code")

    existing_link: Optional[CommLink] = db.get(CommLink, code)
    if existing_link is not None:
        return {"link_code": code, "existed": True}

    link = CommLink(
        link_code=code,
        link_name=payload.get("link_name") or payload.get("name") or code,
        capacity_gbps=payload.get("capacity_gbps", 10.00),
        warning_gbps=payload.get("warning_gbps", 8.00),
        oper_state=payload.get("oper_state", "up"),
        avg_repair_min=payload.get("avg_repair_min", 30),
        lookahead_min=payload.get("lookahead_min", 30),
        backup_link_code=payload.get("backup_link_code"),
        warn_status="正常",
    )
    db.add(link)
    db.flush()
    # R7：新增对象登记后触发 ACT-02 全局重算
    recalc_all(db, as_of_min=get_clock().now_min())
    return {"link_code": code, "triggered_action": "ACT-02"}


def _dispatch_parsed(db: Session, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """根据 parse_input 结果分派到具体 service。"""
    from app.services.repair import handle_repair_update
    from app.services.restore import handle_link_restored

    if parsed.get("category") is None:
        raise ValueError(parsed.get("message", "未识别指令"))

    sub: Optional[str] = parsed.get("sub_type")
    params: Dict[str, Any] = parsed.get("params", {})
    minute_offset: Optional[int] = parsed.get("minute_offset")

    # 预订：写 comm_event，到点兑现
    if minute_offset is not None and sub in ("link_down", "performance_degrade", "demand_change"):
        now = get_clock().now_min()
        occur = now + int(minute_offset)
        ts_suffix: str = datetime.now().strftime("%H%M%S%f")
        if sub in ("link_down", "performance_degrade"):
            ref_type = "alarm"
            ref_code = params.get("link_code")
            summary = f"{minute_offset} 分钟后 {sub} -> {params.get('link_code')}"
        else:
            ref_type = "demand"
            # 唯一 ref_code（带时间戳），编码 task= / gbps=
            ref_code = f"D-{params['task_code'][2:]}-BK{ts_suffix}"
            summary = (
                f"task={params['task_code']};gbps={params['demand_gbps']};"
                f"{minute_offset} 分钟后需求变更"
            )
        ev = SceneEvent(
            event_code=f"EVT-BK-{ts_suffix}",
            event_type="task_booked",
            ref_type=ref_type,
            ref_code=ref_code,
            occur_min=occur,
            summary=summary,
        )
        db.add(ev)
        return {"booking": {"event_code": ev.event_code, "occur_min": occur}}

    # 即时分派
    if sub in ("link_down", "performance_degrade"):
        from app.services.repair import request_repair  # noqa: F401
        # 直接走 ACT-01 + ACT-03 链
        link_code = params["link_code"]
        link = db.get(CommLink, link_code)
        if link is None:
            raise ValueError(f"链路不存在: {link_code}")
        # 注入告警 + 切换 + 生成方案
        seq = len(list(db.scalars(select(ResourceAlarm)))) + 1
        alarm = ResourceAlarm(
            alarm_code=f"AL-{seq:02d}",
            link_code=link_code,
            alarm_type=params.get("alarm_type", "link_down"),
            native_severity=params.get("native_severity", "critical"),
            event_min=get_clock().now_min(),
        )
        db.add(alarm)
        db.flush()
        # 补 alarm_injected 事件流水（同 /api/comm/alarm 路由语义）。
        db.add(
            SceneEvent(
                event_code=f"EVT-AI-{datetime.now().strftime('%H%M%S%f')}",
                event_type="alarm_injected",
                ref_type="alarm",
                ref_code=alarm.alarm_code,
                occur_min=get_clock().now_min(),
                summary=f"{alarm.alarm_code} {alarm.alarm_type} @ {link_code}",
            )
        )
        switch_result = handle_link_down(db, link_code)
        plans = generate_plans_for_alarm(db, alarm.alarm_code)
        return {
            "alarm_code": alarm.alarm_code,
            "switch": switch_result,
            "plans": [p.plan_code for p in plans],
        }
    if sub == "demand_change":
        seq = len(list(db.scalars(select(TrafficDemand)))) + 1
        demand_code = f"D-{params['task_code'][2:]}-{seq:02d}"
        valid_from = params.get("valid_from_min") or get_clock().now_min()
        new_d = TrafficDemand(
            demand_code=demand_code,
            task_code=params["task_code"],
            valid_from_min=valid_from,
            demand_gbps=params["demand_gbps"],
            valid_to_min=None,
        )
        db.add(new_d)
        recalc_all(db, as_of_min=get_clock().now_min())
        return {"demand_code": demand_code, "triggered_action": "ACT-02"}
    if sub == "link_restored":
        return handle_link_restored(db, params["link_code"])
    if sub == "repair_receipt":
        if not params.get("order_code"):
            raise ValueError("缺少 order_code")
        result = handle_repair_update(
            db,
            order_code=params["order_code"],
            est_finish_min=params.get("est_finish_min"),
        )
        return result

    raise ValueError(f"未实现的 sub_type: {sub}")


# =====================================================================
# 兼容旧接口
# =====================================================================

def scene_state(db: Optional[Session] = None) -> Dict[str, Any]:
    """兼容旧调用：轻量状态。"""
    if db is None:
        db = SessionLocal()
        try:
            return get_state(db)
        finally:
            db.close()
    return get_state(db)


async def engine_loop(stop_event: Optional[asyncio.Event] = None) -> None:
    """兼容旧调用：直接驱动 _engine_loop。stop_event 兼容但实际用 cancel。"""
    if stop_event is None:
        await _engine_loop()
        return
    while not stop_event.is_set():
        try:
            await _tick_once()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            try:
                await get_hub().broadcast("engine_error", {"error": str(exc)})
            except Exception:
                pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_TICK_SECONDS)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            return


def reset_tick_cursor() -> None:
    """兼容旧调用。"""
    global _LAST_TICK_AT
    _LAST_TICK_AT = None
    _CONSUMED_EVENTS.clear()
