"""修理单 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RepairOrder(Base):
    """comm_repair_order 表。"""

    __tablename__ = "comm_repair_order"
    __table_args__ = (Index("idx_repair_link", "link_code"),)

    order_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    link_code: Mapped[str] = mapped_column(String(32), nullable=False)
    alarm_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    request_min: Mapped[int] = mapped_column(Integer, nullable=False)
    est_finish_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_finish_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
