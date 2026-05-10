import logging
import time

from dotenv import load_dotenv

from .config import Config
from .core.auth import init_auth
from .core.keys import init_key_store
from .core.kimi_token_store import load_configured_kimi_token
from .core.token_manager import close_token_manager, init_token_manager
from .dashboard.routes import set_start_time
from .kimi.transport import close_shared_transports

logger = logging.getLogger("kimi2api.bootstrap")


def load_runtime_config() -> None:
    load_dotenv()
    Config.load()


def initialize_runtime() -> None:
    raw_token = load_configured_kimi_token()
    if raw_token:
        init_token_manager(raw_token)
    else:
        logger.warning("Kimi token is not configured; set it in /admin/token")

    init_key_store()
    init_auth()
    set_start_time(time.time())


async def shutdown_runtime() -> None:
    await close_token_manager()
    await close_shared_transports()
