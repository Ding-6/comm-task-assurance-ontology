"""通信任务 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import DECIMAL, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommTask(Base):
    """comm_task 表。"""

    __tablename__ = "comm_task"

    task_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    current_link_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    initial_demand_gbps: Mapped[float] = mapped_column(DECIMAL(6, 2), nullable=False)
    lookahead_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
