import os


class Config:
    KIMI_TOKEN: str = ""
    KIMI_API_BASE: str = "https://www.kimi.com"
    TIMEOUT: int = 120
    DEFAULT_MODEL: str = "kimi-k2.5"
    OPENAI_API_KEY: str = ""
    ADMIN_PASSWORD: str = ""
    SESSION_SECRET: str = ""
    SECURE_COOKIES: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False
    DATA_DIR: str = "data"

    @classmethod
    def load(cls) -> None:
        cls.KIMI_TOKEN = os.getenv("KIMI_TOKEN", "")
        cls.KIMI_API_BASE = os.getenv("KIMI_API_BASE", "https://www.kimi.com")
        cls.TIMEOUT = int(os.getenv("TIMEOUT", "120"))
        cls.DEFAULT_MODEL = os.getenv("MODEL", "kimi-k2.5")
        cls.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        cls.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
        cls.SESSION_SECRET = os.getenv("SESSION_SECRET") or ""
        cls.SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true").lower() in {"1", "true", "yes", "on"}
        cls.HOST = os.getenv("HOST", "127.0.0.1")
        cls.PORT = int(os.getenv("PORT", "8000"))
        cls.RELOAD = os.getenv("RELOAD", "").lower() in {"1", "true", "yes", "on"}
        cls.DATA_DIR = os.getenv("DATA_DIR", "data")
