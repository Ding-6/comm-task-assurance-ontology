"""场景时钟：以真实时间为锚点计算当前相对分钟。"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional


class SceneClock:
    """场景时钟单例。"""

    _instance: Optional["SceneClock"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "SceneClock":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self.start_wallclock: Optional[datetime] = None
        self.is_paused: bool = False

    def start(self) -> None:
        """记录当前真实时间为锚点。"""
        self.start_wallclock = datetime.now()
        self.is_paused = False

    def pause(self) -> None:
        """暂停 tick 扫描。业务时钟仍按真实时间推进。"""
        self.is_paused = True

    def resume(self) -> None:
        """恢复 tick 扫描。"""
        self.is_paused = False

    def reset(self) -> None:
        """清空锚点。"""
        self.start_wallclock = None
        self.is_paused = False

    def now_min(self) -> int:
        """当前相对分钟数；未启动返回 0。"""
        if self.start_wallclock is None:
            return 0
        delta = (datetime.now() - self.start_wallclock).total_seconds()
        return int(delta // 60)

    def is_running(self) -> bool:
        """场景是否在跑。"""
        return self.start_wallclock is not None


clock: SceneClock = SceneClock()


def get_clock() -> SceneClock:
    """获取场景时钟单例。"""
    return clock
