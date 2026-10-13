"""审批记录 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApprovalRecord(Base):
    """comm_approval 表。"""

    __tablename__ = "comm_approval"
    __table_args__ = (Index("idx_approval_plan", "plan_code"),)

    approval_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    approver: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    decided_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
