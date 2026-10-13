"""SQLAlchemy ORM 模型集合。

通过显式 import 让 Base.metadata 能识别所有模型，便于 metadata.create_all 或反射。
"""
from app.models.task import CommTask
from app.models.link import CommLink
from app.models.demand import TrafficDemand
from app.models.alarm import ResourceAlarm
from app.models.task_link import TaskLinkBinding
from app.models.approval import ApprovalRecord
from app.models.plan import CommPlan
from app.models.repair_order import RepairOrder
from app.models.event import SceneEvent

__all__ = [
    "CommTask",
    "CommLink",
    "TrafficDemand",
    "ResourceAlarm",
    "TaskLinkBinding",
    "ApprovalRecord",
    "CommPlan",
    "RepairOrder",
    "SceneEvent",
]
