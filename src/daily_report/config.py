"""应用配置：全部来自环境变量或 .env，仓库只保留占位符。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_secret_key: str = Field(alias="APP_SECRET_KEY")
    app_timezone: str = Field(default="Asia/Shanghai", alias="APP_TIMEZONE")

    database_url: str = Field(default="sqlite:///./data/daily_report.db", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    llm_provider: str = Field(default="deepseek", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.deepseek.com", alias="LLM_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=20.0, alias="LLM_TIMEOUT_SECONDS")

    feishu_app_id: str = Field(default="", alias="FEISHU_APP_ID")
    feishu_app_secret: str = Field(default="", alias="FEISHU_APP_SECRET")
    feishu_redirect_uri: str = Field(
        default="http://localhost:8000/api/oauth/feishu/callback", alias="FEISHU_REDIRECT_URI"
    )
    feishu_api_base: str = Field(default="https://open.feishu.cn", alias="FEISHU_API_BASE")
    frontend_base_url: str = Field(default="http://localhost:5173", alias="FRONTEND_BASE_URL")

    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_api_base: str = Field(default="https://api.github.com", alias="GITHUB_API_BASE")
    github_repos: str = Field(default="", alias="GITHUB_REPOS")
    github_login: str = Field(default="", alias="GITHUB_LOGIN")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")

    mock_mode: bool = Field(default=True, alias="MOCK_MODE")
    daily_run_hour: int = Field(default=17, alias="DAILY_RUN_HOUR")
    daily_run_minute: int = Field(default=30, alias="DAILY_RUN_MINUTE")

    @property
    def github_repo_list(self) -> list[str]:
        return [repo.strip() for repo in self.github_repos.split(",") if repo.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 由环境变量提供 APP_SECRET_KEY
