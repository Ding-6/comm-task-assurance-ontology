"""应用配置：读取 .env 中的 MySQL 连接参数。"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置项。"""

    # MySQL 连接
    tma_mysql_host: str = Field(default="172.17.6.242", alias="TMA_MYSQL_HOST")
    tma_mysql_port: int = Field(default=5904, alias="TMA_MYSQL_PORT")
    tma_mysql_user: str = Field(default="", alias="TMA_MYSQL_USER")
    tma_mysql_password: str = Field(default="", alias="TMA_MYSQL_PASSWORD")
    tma_mysql_db: str = Field(default="zb_db2", alias="TMA_MYSQL_DB")

    # 引擎参数
    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle: int = 3600
    charset: str = "utf8mb4"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def sqlalchemy_database_uri(self) -> str:
        """构造 SQLAlchemy 连接 URI。"""
        return (
            f"mysql+pymysql://{self.tma_mysql_user}:{self.tma_mysql_password}"
            f"@{self.tma_mysql_host}:{self.tma_mysql_port}/{self.tma_mysql_db}"
            f"?charset={self.charset}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """缓存配置实例。"""
    return Settings()
