def token_preview(token: str) -> str:
    value = token.strip()
    if len(value) <= 6:
        return "****"
    return f"{value[:3]}****{value[-3:]}"


def token_type_label(token_type: str) -> str:
    normalized = token_type.strip().lower()
    if normalized == "jwt":
        return "access token"
    if normalized == "refresh":
        return "refresh token"
    return normalized or "unknown"
