from typing import Optional

from fastapi import Header, HTTPException, status

from ..core.keys import validate_api_key as _validate_api_key


async def verify_api_key(
    authorization: Optional[str] = Header(default=None),
) -> None:
    api_key = _validate_api_key(authorization)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid API key" if authorization else "Missing bearer token",
                "type": "invalid_request_error",
            },
        )
