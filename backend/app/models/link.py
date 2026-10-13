"""通信链路 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import DECIMAL, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommLink(Base):
    """comm_link 表。"""

    __tablename__ = "comm_link"

    link_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    link_name: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity_gbps: Mapped[float] = mapped_column(DECIMAL(6, 2), nullable=False)
    warning_gbps: Mapped[float] = mapped_column(DECIMAL(6, 2), nullable=False)
    oper_state: Mapped[str] = mapped_column(String(16), nullable=False)
    avg_repair_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lookahead_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    backup_link_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    current_load_gbps: Mapped[Optional[float]] = mapped_column(DECIMAL(6, 2), nullable=True)
    future_load_gbps: Mapped[Optional[float]] = mapped_column(DECIMAL(6, 2), nullable=True)
    warn_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
