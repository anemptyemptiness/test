from pydantic_settings import BaseSettings, SettingsConfigDict
from aiogram.fsm.storage.redis import Redis


class Settings(BaseSettings):
    TOKEN: str

    REVENUE_CHAT_ID: int

    ADMIN_ID: int

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    REDIS_HOST: str

    DAYS_FOR_FINANCES_CHECK: int

    @property
    def get_url_asyncpg(self):
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file="../.env")  # при .env не работает, но надо сделать так, чтоб смогло


settings = Settings()
redis = Redis(host=settings.REDIS_HOST)
