"""输入框自然语言意图识别（事故类 + 提示类）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ---------- 词典 ----------

LINK_KEYWORDS: Dict[str, str] = {
    # L-1H
    "线路1": "L-1H", "1号线路": "L-1H", "1号": "L-1H", "1号线": "L-1H",
    "L-1H": "L-1H", "L1H": "L-1H",
    # L-2H
    "线路2": "L-2H", "2号线路": "L-2H", "2号": "L-2H", "2号线": "L-2H",
    "L-2H": "L-2H", "L2H": "L-2H",
    # L-3H
    "线路3": "L-3H", "3号线路": "L-3H", "3号": "L-3H", "3号线": "L-3H",
    "L-3H": "L-3H", "L3H": "L-3H",
}

TASK_KEYWORDS: Dict[str, str] = {
    "直播": "T-B",
    "指挥": "T-A",
    "既有": "T-C",
}

# 预订时间匹配：N分钟后 / N分后 / N分钟后
_OFFSET_RE = re.compile(r"(\d+)\s*分(?:钟)?\s*后")
# G 数值匹配：到6G / 提到7G / 需 6 G / 6.0G
_VALUE_RE = re.compile(r"(?:到|提(?:到|高)?|需|变成|为|约|是)\s*(\d+(?:\.\d+)?)\s*G", re.IGNORECASE)
_VALUE_LOOSE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*G\b", re.IGNORECASE)
# 修理预计时长：预计55分钟完成 / 预计55分修好 / 55分修好
_EST_RE = re.compile(r"(?:预计|约)?\s*(\d+)\s*(?:分钟|分)(?:完成|修好|修复|完成)?")


# ---------- 识别失败时的可点选建议 ----------
# 前端收到 category=null 时展示该列表，用户点击其中一项等价于把
# message 文本替换为对应 example 再次提交，从而让系统不会猜测。
SUGGESTIONS: List[Dict[str, str]] = [
    {
        "sub_type": "link_down",
        "label": "线路故障",
        "example": "线路1故障 / 20分钟后L-2H故障",
    },
    {
        "sub_type": "performance_degrade",
        "label": "性能劣化",
        "example": "L-2H性能劣化",
    },
    {
        "sub_type": "demand_change",
        "label": "需求变更",
        "example": "50分钟后直播需求到6G",
    },
    {
        "sub_type": "link_restored",
        "label": "链路恢复",
        "example": "线路1修好了",
    },
    {
        "sub_type": "repair_receipt",
        "label": "修理回执",
        "example": "修理单预计55分钟完成",
    },
]


def _extract_link(text: str) -> Optional[str]:
    """从文本里识别链路编码。"""
    # 1. 规范化 L-xH / LxH → L-{1|2|3}H
    m = re.search(r"L-?([123])H", text, re.IGNORECASE)
    if m:
        return f"L-{m.group(1)}H"

    # 2. 中文关键词
    for kw, code in LINK_KEYWORDS.items():
        if kw in text:
            return code
    return None


def _extract_task(text: str) -> Optional[str]:
    for kw, code in TASK_KEYWORDS.items():
        if kw in text:
            return code
    return None


def _extract_minute_offset(text: str) -> Optional[int]:
    m = _OFFSET_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _extract_value_gbps(text: str) -> Optional[float]:
    m = _VALUE_RE.search(text)
    if m:
        return float(m.group(1))
    m2 = _VALUE_LOOSE_RE.search(text)
    if m2:
        return float(m2.group(1))
    return None


def _extract_est_finish(text: str) -> Optional[int]:
    m = _EST_RE.search(text)
    if m:
        return int(m.group(1))
    return None


# ---------- 主函数 ----------

def parse_input(text: str) -> Dict[str, Any]:
    """自然语言 → 结构化动作。

    成功识别：
        {
          "category": "alarm" | "notice",
          "sub_type": str,
          "link_code": str | None,
          "task_code": str | None,
          "minute_offset": int | None,
          "value": float | None,
          "est_finish_min": int | None,
          "action": str,
          "params": dict,
          "raw": str,
          "message": None,
        }

    识别失败（category=None）：
        {
          "category": None,
          "sub_type": None,
          "message": "无法识别：缺少线路编号或任务名。系统不会猜测，也不会执行。",
          "suggestions": [
            {"sub_type": "...", "label": "...", "example": "..."},
            ...
          ],
          "raw": str,
        }
        —— 不携带 link_code / task_code / action 等业务字段，
           前端收到后展示 suggestions 让用户点选，不直接执行。
    """
    raw: str = (text or "").strip()
    t: str = raw
    lower: str = t.lower()

    # ---------- 1. 链路恢复 ----------
    if ("恢复" in t or "修好" in t or "复原" in t) and (
        "已" in t or "已恢复" in t or "好了" in t or "完成" in t
    ):
        link_code = _extract_link(t)
        if link_code is not None:
            return {
                "category": "notice",
                "sub_type": "link_restored",
                "link_code": link_code,
                "task_code": None,
                "minute_offset": None,
                "value": None,
                "est_finish_min": None,
                "action": "POST /api/comm/restore",
                "params": {"link_code": link_code},
                "raw": raw,
                "message": None,
            }

    # ---------- 2. 修理回执 ----------
    if "回执" in t or "预计" in t and "修" in t or "修好" in t or "完成" in t and "修理" in t:
        # 优先从显式 order_code 取
        m_order = re.search(r"RP-[\w\-]+", t)
        order_code: Optional[str] = m_order.group(0) if m_order else None
        est = _extract_est_finish(t)
        if order_code or est is not None:
            return {
                "category": "notice",
                "sub_type": "repair_receipt",
                "link_code": _extract_link(t),
                "task_code": None,
                "minute_offset": None,
                "value": None,
                "est_finish_min": est,
                "action": "POST /api/comm/repair",
                "params": {
                    "order_code": order_code,
                    "est_finish_min": est,
                },
                "raw": raw,
                "message": None,
            }

    # ---------- 3. 需求变更（提示类） ----------
    if any(k in t for k in ("需求", "带宽", "流量")) and any(
        k in t for k in ("到", "提", "降", "加", "需")
    ):
        task_code = _extract_task(t)
        value = _extract_value_gbps(t)
        minute_offset = _extract_minute_offset(t)
        if task_code and value is not None:
            return {
                "category": "notice",
                "sub_type": "demand_change",
                "link_code": None,
                "task_code": task_code,
                "minute_offset": minute_offset,
                "value": value,
                "est_finish_min": None,
                "action": "POST /api/comm/demand",
                "params": {
                    "task_code": task_code,
                    "demand_gbps": value,
                    "valid_from_min": minute_offset,  # None=即时
                },
                "raw": raw,
                "message": None,
            }

    # ---------- 4. 性能劣化（事故类，需独立分支：不依赖"故障"字眼） ----------
    if "性能" in t and ("劣化" in t or "降级" in t or "下降" in t):
        link_code = _extract_link(t)
        if link_code is not None:
            minute_offset = _extract_minute_offset(t)
            return {
                "category": "alarm",
                "sub_type": "performance_degrade",
                "link_code": link_code,
                "task_code": None,
                "minute_offset": minute_offset,
                "value": None,
                "est_finish_min": None,
                "action": "POST /api/comm/alarm",
                "params": {
                    "link_code": link_code,
                    "alarm_type": "性能劣化",
                    "native_severity": "critical",
                    "minute_offset": minute_offset,
                },
                "raw": raw,
                "message": None,
            }

    # ---------- 5. 链路故障（事故类） ----------
    if any(k in t for k in ("故障", "断了", "中断", "挂了", "down")):
        link_code = _extract_link(t)
        if link_code is not None:
            minute_offset = _extract_minute_offset(t)
            return {
                "category": "alarm",
                "sub_type": "link_down",
                "link_code": link_code,
                "task_code": None,
                "minute_offset": minute_offset,
                "value": None,
                "est_finish_min": None,
                "action": "POST /api/comm/alarm",
                "params": {
                    "link_code": link_code,
                    "alarm_type": "link_down",
                    "native_severity": "critical",
                    "minute_offset": minute_offset,  # 预订
                },
                "raw": raw,
                "message": None,
            }

    # ---------- 兜底：识别失败 ----------
    # 不携带 link_code / task_code / action 等业务字段，
    # 前端展示 suggestions 让用户点选，不直接执行。
    return {
        "category": None,
        "sub_type": None,
        "message": "无法识别：缺少线路编号或任务名。系统不会猜测，也不会执行。",
        "suggestions": SUGGESTIONS,
        "raw": raw,
    }


# ---------- 兼容旧接口 ----------

def recognize_intent(text: str) -> Dict[str, Any]:
    """兼容旧调用：粗略归类为动作。"""
    parsed = parse_input(text)
    # 旧字段映射
    intent_map: Dict[str, str] = {
        "link_restored": "restore",
        "repair_receipt": "repair_receipt",
        "demand_change": "demand_change",
        "link_down": "alarm_inject",
        "performance_degrade": "alarm_inject",
    }
    sub = parsed.get("sub_type")
    return {
        "intent": intent_map.get(sub, "unknown") if sub else "unknown",
        "link_code": parsed.get("link_code"),
        "task_code": parsed.get("task_code"),
        "value": parsed.get("value"),
        "est_finish_min": parsed.get("est_finish_min"),
        "raw": parsed.get("raw"),
        "parsed": parsed,
        "hint": parsed.get("message"),
    }
