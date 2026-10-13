"""WebSocket 连接管理：注册、广播、注销。"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Set

from fastapi import WebSocket


class WsHub:
    """WebSocket 连接管理（单例）。"""

    _instance: "WsHub | None" = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "WsHub":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """接受并注册一个连接。"""
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """注销一个连接。"""
        self._clients.discard(ws)

    async def broadcast(self, message_type: str, payload: Any = None) -> None:
        """向所有连接广播一条消息。"""
        if not self._clients:
            return
        msg = json.dumps({"type": message_type, "data": payload}, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub: WsHub = WsHub()


def get_hub() -> WsHub:
    """获取 WS 单例。"""
    return hub
