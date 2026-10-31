from app.backends.common import (
    classify_error,
    error,
    not_found,
    ok,
    router_credentials,
    same_interface,
    to_cidr,
)


DEVICE_TYPE = "cisco_ios"

IP_COMMAND = "show ip interface {interface_name}"
DESCRIPTION_COMMAND = "show interfaces description"
DELETE_COMMAND = "no interface {interface_name}"

ADMIN_DOWN = "administratively down"


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    if netmiko_get is None:
        netmiko_get = _default_netmiko_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
    except Exception as exception:
        return error(classify_error(exception))

    try:
        interface = _normalize(ip_info, descriptions, interface_name)
    except Exception:
        return error("backend_failed")

    if interface is None:
        return not_found()

    return ok("found", interface=interface)


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    if netmiko_delete is None:
        netmiko_delete = _default_netmiko_delete

    try:
        outcome = netmiko_delete(router, interface_name)
    except Exception as exception:
        return error(classify_error(exception))

    if outcome == "deleted":
        return ok("deleted")

    if outcome == "not_found":
        return not_found()

    return error("backend_failed")


def _normalize(ip_info, descriptions, interface_name):
    """Map parsed TextFSM records to the normalized interface."""
    record = _find(ip_info, "interface", interface_name)

    if record is None:
        return None

    return {
        "name": str(interface_name),
        "ipv4": _ipv4(record),
        "description": _description(descriptions, interface_name),
        "admin_state": _admin_state(record),
    }


def _find(records, key, interface_name):
    if not isinstance(records, list):
        raise ValueError("TextFSM records were not parsed into a list")

    for record in records:
        if not isinstance(record, dict):
            continue
        if same_interface(record.get(key, ""), interface_name):
            return record

    return None


def _ipv4(record):
    address = _first(record.get("ip_address"))
    prefix = _first(record.get("prefix_length"))

    if not address:
        return None

    if not prefix:
        return str(address)

    # prefix_length is already a prefix length, not a dotted netmask.
    return to_cidr(address, int(prefix))


def _description(descriptions, interface_name):
    # IOS abbreviates Loopback123 to Lo123 in this command.
    record = _find(descriptions, "port", interface_name)

    if record is None:
        return None

    description = record.get("description")

    if description is None or description == "":
        return None

    return description


def _admin_state(record):
    link_status = str(record.get("link_status", "")).strip().lower()
    return "down" if ADMIN_DOWN in link_status else "up"


def _as_exception(code):
    """Re-raise a backend error code so its meaning survives mapping."""
    if code == "authentication_failed":
        return PermissionError(code)
    if code == "connection_failed":
        return ConnectionError(code)
    return RuntimeError(code)


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _connect(router):
    from netmiko import ConnectHandler

    user, password = router_credentials()

    return ConnectHandler(
        device_type=DEVICE_TYPE,
        host=router,
        username=user,
        password=password,
    )


def _default_netmiko_get(router, interface_name):
    connection = _connect(router)

    try:
        ip_info = connection.send_command(
            IP_COMMAND.format(interface_name=interface_name),
            use_textfsm=True,
        )
        descriptions = connection.send_command(
            DESCRIPTION_COMMAND,
            use_textfsm=True,
        )
    finally:
        connection.disconnect()

    if not isinstance(ip_info, list) or not isinstance(descriptions, list):
        raise RuntimeError("TextFSM could not parse the IOS output")

    return ip_info, descriptions


def _default_netmiko_delete(router, interface_name):
    """Remove the interface and verify that it is gone."""
    before = get_interface_state(router, interface_name)

    if before.get("status") == "error":
        raise _as_exception(before["result"])

    if before.get("result") == "not_found":
        return "not_found"

    connection = _connect(router)

    try:
        connection.send_config_set(
            [DELETE_COMMAND.format(interface_name=interface_name)]
        )
    finally:
        connection.disconnect()

    after = get_interface_state(router, interface_name)

    if after.get("result") != "not_found":
        raise RuntimeError("interface is still present after delete")

    return "deleted"
