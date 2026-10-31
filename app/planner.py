MANAGED_FIELDS = ("ipv4", "description", "admin_state")


def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    changes = {}

    if current_interface is None:
        operation = "create"
        for field in MANAGED_FIELDS:
            changes[field] = {"to": desired_interface.get(field)}
    else:
        for field in MANAGED_FIELDS:
            desired_value = desired_interface.get(field)
            current_value = current_interface.get(field)
            if current_value != desired_value:
                changes[field] = {
                    "from": current_value,
                    "to": desired_value,
                }
        operation = "update" if changes else "no_change"

    return {
        "status": "ok",
        "result": "planned",
        "operation": operation,
        "changes": changes,
    }
