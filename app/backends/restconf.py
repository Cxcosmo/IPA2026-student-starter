from app.backends.common import (
    classify_error,
    error,
    loopback_number,
    not_found,
    ok,
    router_credentials,
    split_cidr,
    to_cidr,
)
from app.backends.planning import plan_interface as _plan_interface


STATUS_URL = (
    "https://{router}/restconf/data/"
    "ietf-interfaces:interfaces/interface={interface_name}"
)

APPLY_URL = (
    "https://{router}/restconf/data/"
    "Cisco-IOS-XE-native:native/interface/Loopback={number}"
)

YANG_JSON = "application/yang-data+json"

APPLY_SUCCESS_CODES = (200, 201, 204)
AUTHENTICATION_CODES = (401, 403)

REQUEST_TIMEOUT = 10


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    if http_get is None:
        http_get = _default_http_get

    url = STATUS_URL.format(
        router=router,
        interface_name=interface_name,
    )

    try:
        response = http_get(url)
    except Exception as exception:
        return error(classify_error(exception))

    status_code = getattr(response, "status_code", None)

    if status_code == 404:
        return not_found()

    if status_code in AUTHENTICATION_CODES:
        return error("authentication_failed")

    if status_code not in (200, 204):
        return error("backend_failed")

    try:
        interface = _normalize(response.json())
    except Exception:
        return error("backend_failed")

    if interface is None:
        return not_found()

    return ok("found", interface=interface)


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    def status(router_address, interface_name):
        return get_interface_state(
            router_address,
            interface_name,
            http_get,
        )

    return _plan_interface(router, desired_interface, status)


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    if http_put is None:
        http_put = _default_http_put

    try:
        number = loopback_number(desired_interface["name"])
        payload = build_native_payload(desired_interface, number)
    except (KeyError, ValueError):
        return error("backend_failed")

    url = APPLY_URL.format(router=router, number=number)

    try:
        response = http_put(url, json=payload)
    except Exception as exception:
        return error(classify_error(exception))

    status_code = getattr(response, "status_code", None)

    if status_code in AUTHENTICATION_CODES:
        return error("authentication_failed")

    if status_code not in APPLY_SUCCESS_CODES:
        return error("backend_failed")

    return ok("applied")


def build_native_payload(desired_interface, number):
    """Map the normalized desired state to Cisco-IOS-XE-native."""
    address, netmask = split_cidr(desired_interface["ipv4"])

    loopback = {
        "name": number,
        "description": desired_interface["description"],
        "ip": {
            "address": {
                "primary": {
                    "address": address,
                    "mask": netmask,
                },
            },
        },
    }

    # The native model expresses "shutdown" as a presence leaf, so it is
    # only included when the interface must be administratively down.
    if desired_interface.get("admin_state") == "down":
        loopback["shutdown"] = [None]

    return {"Cisco-IOS-XE-native:Loopback": loopback}


def _normalize(data):
    """Map ietf-interfaces/ietf-ip data to the normalized interface."""
    if not isinstance(data, dict):
        raise ValueError("RESTCONF response is not a JSON object")

    interface = data.get("ietf-interfaces:interface")
    if interface is None:
        interface = data.get("interface")

    if isinstance(interface, list):
        interface = interface[0] if interface else None

    if not isinstance(interface, dict):
        return None

    ipv4 = interface.get("ietf-ip:ipv4") or interface.get("ipv4") or {}
    addresses = ipv4.get("address") or []

    address = None
    if addresses:
        first = addresses[0]
        address = to_cidr(first["ip"], first["netmask"])

    return {
        "name": interface.get("name"),
        "ipv4": address,
        "description": interface.get("description"),
        "admin_state": "up" if interface.get("enabled") else "down",
    }


def _session():
    import requests
    import urllib3

    urllib3.disable_warnings(
        urllib3.exceptions.InsecureRequestWarning
    )

    session = requests.Session()
    session.auth = router_credentials()
    session.verify = False
    session.headers.update({
        "Accept": YANG_JSON,
        "Content-Type": YANG_JSON,
    })

    return session


def _default_http_get(url):
    return _session().get(url, timeout=REQUEST_TIMEOUT)


def _default_http_put(url, json):
    return _session().put(url, json=json, timeout=REQUEST_TIMEOUT)
