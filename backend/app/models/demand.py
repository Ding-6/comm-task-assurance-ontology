"""流量需求 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import DECIMAL, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrafficDemand(Base):
    """comm_demand 表。"""

    __tablename__ = "comm_demand"
    __table_args__ = (Index("idx_demand_task", "task_code"),)

    demand_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_code: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from_min: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_gbps: Mapped[float] = mapped_column(DECIMAL(6, 2), nullable=False)
    valid_to_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
