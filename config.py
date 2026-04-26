from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: list[int]
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

settings = Settings()
