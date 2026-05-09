from collections import deque
from dataclasses import dataclass
from typing import List

BUFFER_SIZE = 1000

_logs: deque = deque(maxlen=BUFFER_SIZE)


@dataclass
class RequestLog:
    timestamp: float
    api_key_name: str
    model: str
    status: str
    status_code: int
    duration_ms: float
    is_stream: bool = False


def log_request(entry: RequestLog) -> None:
    _logs.append(entry)


def get_recent_logs(limit: int = 100) -> List[RequestLog]:
    items = list(_logs)
    items.reverse()
    return items[:limit]


def total_log_count() -> int:
    return len(_logs)
