"""后端启动入口。"""
from __future__ import annotations

import uvicorn

from app.main import app


def main() -> None:
    """运行 uvicorn 启动 FastAPI 应用。"""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
