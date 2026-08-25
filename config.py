import json
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: Annotated[list[int], NoDecode] = Field(default_factory=list)
    DATABASE_URL: str = 'sqlite+aiosqlite:///data/database.db'

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, value: Any) -> list[int]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith('['):
                return [int(admin_id) for admin_id in json.loads(value)]
            return [int(admin_id.strip()) for admin_id in value.split(',')]
        return value

    @model_validator(mode='after')
    def validate_required_admins(self):
        if not self.ADMIN_IDS:
            raise ValueError('ADMIN_IDS must contain at least one Telegram user ID')
        return self


settings = Settings()
