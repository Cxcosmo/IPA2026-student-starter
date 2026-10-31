import yaml


ALLOWED_ROUTERS = (
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
)

METHOD_ACTIONS = {
    "restconf": ("status", "plan", "apply"),
    "netconf": ("status", "plan", "apply"),
    "ansible": ("apply",),
    "netmiko-textfsm": ("status", "delete"),
}

ALLOWED_ADMIN_STATES = ("up", "down")

COMPLETE_STATE_ACTIONS = ("plan", "apply")


def _error(code):
    return {"status": "error", "result": code}


def _get(mapping, key):
    """Return mapping[key], or None when absent or not a mapping."""
    if not isinstance(mapping, dict):
        return None
    return mapping.get(key)


def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return _error("invalid_yaml")

    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        return _error("invalid_version")

    router = data.get("router")
    if router is None:
        return _error("missing_router")
    if router not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    method = data.get("method")
    if method is None:
        return _error("missing_method")
    if method not in METHOD_ACTIONS:
        return _error("invalid_method")

    action = data.get("action")
    if action is None:
        return _error("missing_action")
    if action not in METHOD_ACTIONS[method]:
        return _error("invalid_action")

    desired = data.get("desired")
    if desired is None:
        return _error("missing_desired")

    interface = _get(desired, "interface")
    if interface is None:
        return _error("missing_interface")

    if _get(interface, "name") is None:
        return _error("missing_interface_name")

    if action in COMPLETE_STATE_ACTIONS:
        if _get(interface, "ipv4") is None:
            return _error("missing_ipv4")
        if _get(interface, "description") is None:
            return _error("missing_description")

        admin_state = _get(interface, "admin_state")
        if admin_state is None:
            return _error("missing_admin_state")
        if admin_state not in ALLOWED_ADMIN_STATES:
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return _error("invalid_yaml")

    if not isinstance(data, dict):
        return _error("invalid_yaml")

    return validate_request(data)
