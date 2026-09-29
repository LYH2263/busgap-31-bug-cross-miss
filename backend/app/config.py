from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+psycopg2://busgap:busgap@localhost:5447/busgap"
    seed_on_empty: bool = True


settings = Settings()
