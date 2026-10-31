import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

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


NETCONF_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"
INTERFACES_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"
NATIVE_NS = "http://cisco.com/ns/yang/Cisco-IOS-XE-native"

NETCONF_PORT = 830
CONNECT_TIMEOUT = 20

STATUS_FILTER = (
    '<interfaces xmlns="{interfaces_ns}">'
    "<interface>"
    "<name>{interface_name}</name>"
    "</interface>"
    "</interfaces>"
)


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    if netconf_get_config is None:
        netconf_get_config = _default_get_config

    filter_xml = STATUS_FILTER.format(
        interfaces_ns=INTERFACES_NS,
        interface_name=escape(str(interface_name)),
    )

    try:
        reply_xml = netconf_get_config(router, filter_xml)
    except Exception as exception:
        return error(classify_error(exception))

    try:
        interface = _normalize(reply_xml, interface_name)
    except Exception:
        return error("backend_failed")

    if interface is None:
        return not_found()

    return ok("found", interface=interface)


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    def status(router_address, interface_name):
        return get_interface_state(
            router_address,
            interface_name,
            netconf_get_config,
        )

    return _plan_interface(router, desired_interface, status)


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    if netconf_edit_config is None:
        netconf_edit_config = _default_edit_config

    try:
        config_xml = build_native_config(desired_interface)
    except (KeyError, ValueError):
        return error("backend_failed")

    try:
        netconf_edit_config(router, config_xml)
    except Exception as exception:
        return error(classify_error(exception))

    return ok("applied")


def build_native_config(desired_interface):
    """Build a Cisco-IOS-XE-native edit-config payload."""
    number = loopback_number(desired_interface["name"])
    address, netmask = split_cidr(desired_interface["ipv4"])

    # The whole Loopback entry is replaced so a previous primary address
    # cannot survive as a stale secondary address.
    shutdown = ""
    if desired_interface.get("admin_state") == "down":
        shutdown = "<shutdown/>"

    return (
        f'<config xmlns="{NETCONF_NS}" xmlns:nc="{NETCONF_NS}">'
        f'<native xmlns="{NATIVE_NS}">'
        "<interface>"
        '<Loopback nc:operation="replace">'
        f"<name>{number}</name>"
        f"<description>"
        f"{escape(str(desired_interface['description']))}"
        f"</description>"
        "<ip><address><primary>"
        f"<address>{address}</address>"
        f"<mask>{netmask}</mask>"
        "</primary></address></ip>"
        f"{shutdown}"
        "</Loopback>"
        "</interface>"
        "</native>"
        "</config>"
    )


def _normalize(reply_xml, interface_name):
    """Map ietf-interfaces/ietf-ip XML to the normalized interface."""
    root = ET.fromstring(reply_xml)

    for element in root.iter(f"{{{INTERFACES_NS}}}interface"):
        name = _text(element, f"{{{INTERFACES_NS}}}name")

        if name is None or name != str(interface_name):
            continue

        enabled = _text(element, f"{{{INTERFACES_NS}}}enabled")

        return {
            "name": name,
            "ipv4": _ipv4(element),
            "description": _text(
                element,
                f"{{{INTERFACES_NS}}}description",
            ),
            "admin_state": "down" if enabled == "false" else "up",
        }

    return None


def _ipv4(interface_element):
    address = interface_element.find(
        f"{{{IP_NS}}}ipv4/{{{IP_NS}}}address"
    )

    if address is None:
        return None

    ip = _text(address, f"{{{IP_NS}}}ip")
    netmask = _text(address, f"{{{IP_NS}}}netmask")

    if ip is None or netmask is None:
        return None

    return to_cidr(ip, netmask)


def _text(element, path):
    found = element.find(path)

    if found is None or found.text is None:
        return None

    return found.text.strip()


def _manager(router):
    from ncclient import manager

    user, password = router_credentials()

    return manager.connect(
        host=router,
        port=NETCONF_PORT,
        username=user,
        password=password,
        hostkey_verify=False,
        look_for_keys=False,
        allow_agent=False,
        timeout=CONNECT_TIMEOUT,
        device_params={"name": "iosxe"},
    )


def _default_get_config(router, filter_xml):
    with _manager(router) as session:
        return session.get(filter=("subtree", filter_xml)).data_xml


def _default_edit_config(router, config_xml):
    with _manager(router) as session:
        session.edit_config(target="running", config=config_xml)
