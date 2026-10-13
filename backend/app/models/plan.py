"""处置方案 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import DECIMAL, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommPlan(Base):
    """comm_plan 表。"""

    __tablename__ = "comm_plan"
    __table_args__ = (Index("idx_plan_alarm", "alarm_code"),)

    plan_code: Mapped[str] = mapped_column(String(128), primary_key=True)
    alarm_code: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(16), nullable=False)
    link_code: Mapped[str] = mapped_column(String(32), nullable=False)
    target_link_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    est_repair_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    predicted_load_after_gbps: Mapped[Optional[float]] = mapped_column(
        DECIMAL(6, 2), nullable=True
    )
    can_meet_critical: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_default: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    generated_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
