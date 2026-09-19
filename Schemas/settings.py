from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SERVICENOW_INSTANCE_URL: str
    SERVICENOW_USERNAME: str
    SERVICENOW_PASSWORD: str
    SERVICENOW_KB_ID: str
    SERVICENOW_KB_CATEGORY_ID: str
    API_SECRET_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()