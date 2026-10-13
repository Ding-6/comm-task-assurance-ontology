"""场景事件流水 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SceneEvent(Base):
    """comm_event 表。"""

    __tablename__ = "comm_event"
    __table_args__ = (
        Index("idx_event_type", "event_type"),
        Index("idx_event_occur", "occur_min"),
    )

    event_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ref_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    occur_min: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
