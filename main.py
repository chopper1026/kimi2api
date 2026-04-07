import os

import uvicorn
from dotenv import load_dotenv

from kimi2api import create_app

load_dotenv()


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload_enabled = os.getenv("RELOAD", "").lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        factory=False,
    )


app = create_app()


if __name__ == "__main__":
    main()
