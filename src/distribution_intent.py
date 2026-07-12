"""Normalize user-requested distribution constraints for idea generation."""

VALID_MODES = {"open", "platform_constrained", "exact_format"}


def _as_clean_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("platforms and formats must be strings or lists")
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_distribution_intent(payload: dict | None) -> dict:
    """Return the canonical distribution-intent contract.

    The API accepts either the explicit nested contract or the UI-friendly
    singular ``platform`` / ``format`` fields. A format plus platform is an
    exact user constraint; a platform alone lets the LLM choose within it.
    """
    payload = payload or {}
    explicit = payload.get("distribution_intent")

    if explicit is not None:
        if not isinstance(explicit, dict):
            raise ValueError("distribution_intent must be an object")
        mode = str(explicit.get("mode", "open")).strip()
        platforms = _as_clean_list(explicit.get("platforms"))
        formats = _as_clean_list(explicit.get("formats"))
    else:
        platforms = _as_clean_list(payload.get("platform"))
        formats = _as_clean_list(payload.get("format"))
        if formats:
            mode = "exact_format"
        elif platforms:
            mode = "platform_constrained"
        else:
            mode = "open"

    if mode not in VALID_MODES:
        raise ValueError(f"Unknown distribution intent mode: {mode}")
    if mode == "open":
        platforms, formats = [], []
    elif mode == "platform_constrained":
        if not platforms:
            raise ValueError("platform_constrained requires at least one platform")
        formats = []
    elif len(platforms) != 1 or len(formats) != 1:
        raise ValueError("exact_format requires exactly one platform and one format")

    return {"mode": mode, "platforms": platforms, "formats": formats}
