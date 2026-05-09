from fastapi.responses import JSONResponse


def _json_error(message: str, error_type: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": None,
                "code": error_type,
            }
        },
    )
