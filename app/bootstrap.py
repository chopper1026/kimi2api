import logging
import time

from dotenv import load_dotenv

from .config import Config
from .core.auth import init_auth
from .core.kimi_account_pool import close_account_pool, init_account_pool
from .core.kimi_account_store import kimi_accounts_file_exists, load_kimi_accounts
from .core.keys import init_key_store
from .core.kimi_token_store import load_configured_kimi_token
from .core.token_manager import close_token_manager, init_token_manager
from .dashboard.view_models import set_start_time
from .kimi.transport import close_shared_transports

logger = logging.getLogger("kimi2api.bootstrap")


def load_runtime_config() -> None:
    load_dotenv()
    Config.load()


def initialize_runtime() -> None:
    accounts_file_exists = kimi_accounts_file_exists()
    accounts = load_kimi_accounts()
    if accounts:
        init_account_pool(accounts)
        init_token_manager(accounts[0].raw_token)
    elif accounts_file_exists:
        init_account_pool([])
    elif raw_token := load_configured_kimi_token():
        init_token_manager(raw_token)
    else:
        logger.warning("Kimi token is not configured; set it in /admin/token")

    init_key_store()
    init_auth()
    set_start_time(time.time())


async def shutdown_runtime() -> None:
    await close_account_pool()
    await close_token_manager()
    await close_shared_transports()
