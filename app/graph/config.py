from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 统一存储（SQLite 内嵌库，无需外部数据库）：图谱/类型字典/操作记录/实例
    sqlite_url: str = "sqlite:///./data/data.db"
    # CORS 来源（逗号分隔，可空）。留空默认放行全部 localhost 来源（任意端口，开发直连无需配置）
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_allow_localhost(self) -> bool:
        """未配置 CORS_ORIGINS 时默认放行所有 localhost 来源。"""
        return not self.cors_origins.strip()


settings = Settings()
