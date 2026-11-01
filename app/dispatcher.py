"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf


# (method, action) -> (module, function name). The function is resolved with
# getattr when the request is dispatched so the capability matrix stays in
# one place and backends can be substituted in tests.
BACKENDS = {
    ("restconf", "status"): (restconf, "get_interface_state"),
    ("restconf", "plan"): (restconf, "plan_interface"),
    ("restconf", "apply"): (restconf, "apply_interface"),
    ("netconf", "status"): (netconf, "get_interface_state"),
    ("netconf", "plan"): (netconf, "plan_interface"),
    ("netconf", "apply"): (netconf, "apply_interface"),
    ("ansible", "apply"): (ansible, "apply_interface"),
    ("netmiko-textfsm", "status"): (netmiko_textfsm, "get_interface_state"),
    ("netmiko-textfsm", "delete"): (netmiko_textfsm, "delete_interface"),
}

NAME_ONLY_ACTIONS = ("status", "delete")


def dispatch_request(data):
    """Send an already validated request to its backend."""
    method = data["method"]
    action = data["action"]

    target = BACKENDS.get((method, action))

    if target is None:
        return {"status": "error", "result": "invalid_action"}

    module, function_name = target
    backend = getattr(module, function_name)

    router = data["router"]
    interface = data["desired"]["interface"]

    if action in NAME_ONLY_ACTIONS:
        return backend(router, interface["name"])

    return backend(router, interface)
