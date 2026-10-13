"""任务链路归属历史 ORM 模型。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskLinkBinding(Base):
    """comm_task_link 表。

    使用自增 surrogate id 作为主键，避免同一任务在同一分钟内
    多次切换/恢复时 PK 冲突；通过 id 排序得到"最新归属"。

    同步加 (task_code, assigned_min) 唯一约束，对齐说明书 §5.1
    "归属历史全程留痕"语义——保证同一任务在同一分钟只有一条归属，
    多次切换靠 surrogate id 的 id 区分。
    """

    __tablename__ = "comm_task_link"
    __table_args__ = (
        UniqueConstraint("task_code", "assigned_min", name="uk_task_min"),
        Index("idx_task_link_task", "task_code"),
        Index("idx_task_link_link", "link_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(32), nullable=False)
    link_code: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_min: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
