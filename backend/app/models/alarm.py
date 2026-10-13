"""资源告警 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResourceAlarm(Base):
    """comm_alarm 表。"""

    __tablename__ = "comm_alarm"
    __table_args__ = (Index("idx_alarm_link", "link_code"),)

    alarm_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    link_code: Mapped[str] = mapped_column(String(32), nullable=False)
    alarm_type: Mapped[str] = mapped_column(String(32), nullable=False)
    native_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    event_min: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
