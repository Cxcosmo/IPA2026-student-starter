"""Shared helpers for the Part 3 backends."""

import os
from ipaddress import IPv4Interface


LOOPBACK_PREFIX = "Loopback"

AUTHENTICATION_ERRORS = (
    "PermissionError",
    "AuthenticationError",
    "AuthenticationException",
    "NetmikoAuthenticationException",
    "NetMikoAuthenticationException",
    "AnsibleAuthenticationFailure",
)

CONNECTION_ERRORS = (
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "TimeoutError",
    "Timeout",
    "ConnectTimeout",
    "ReadTimeout",
    "ConnectTimeoutError",
    "SSHError",
    "SSHException",
    "NetconfSSHError",
    "NetmikoTimeoutException",
    "NetMikoTimeoutException",
    "AnsibleConnectionFailure",
)


def ok(result, **extra):
    response = {"status": "ok", "result": result}
    response.update(extra)
    return response


def error(code):
    return {"status": "error", "result": code}


def not_found():
    return ok("not_found", interface=None)


def classify_error(exception):
    """
    Map a transport exception to a backend error code.

    The public tests raise PermissionError, ConnectionError and
    RuntimeError. Real libraries raise their own classes, so the whole
    inheritance chain is inspected by class name instead of relying on
    the built-in exception hierarchy.
    """
    for klass in type(exception).__mro__:
        if klass.__name__ in AUTHENTICATION_ERRORS:
            return "authentication_failed"
        if klass.__name__ in CONNECTION_ERRORS:
            return "connection_failed"
    return "backend_failed"


def router_credentials():
    """Return (user, password) from the runtime environment."""
    user = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")

    if not user or not password:
        raise PermissionError(
            "ROUTER_USER and ROUTER_PASS must be set in the environment"
        )

    return user, password


def loopback_number(interface_name):
    """Loopback123 -> 123 (the Cisco native list key)."""
    digits = "".join(
        character
        for character in str(interface_name)
        if character.isdigit()
    )

    if not digits:
        raise ValueError(f"No Loopback number in {interface_name!r}")

    return int(digits)


def split_cidr(cidr):
    """172.23.123.1/32 -> ("172.23.123.1", "255.255.255.255")."""
    address = IPv4Interface(str(cidr))
    return str(address.ip), str(address.network.netmask)


def to_cidr(ip, netmask):
    """("172.23.123.1", "255.255.255.255") -> "172.23.123.1/32"."""
    return IPv4Interface(f"{ip}/{netmask}").with_prefixlen


def same_interface(left, right):
    """
    Compare interface names, tolerating IOS abbreviations.

    `show interfaces description` reports Loopback123 as Lo123, so two
    names match when their numbers are equal and one alphabetic prefix
    is a prefix of the other.
    """
    left_letters, left_digits = _split_name(left)
    right_letters, right_digits = _split_name(right)

    if left_digits != right_digits:
        return False

    return left_letters.startswith(right_letters) or right_letters.startswith(
        left_letters
    )


def _split_name(name):
    text = str(name).strip()
    letters = "".join(c for c in text if c.isalpha()).lower()
    digits = "".join(c for c in text if c.isdigit())
    return letters, digits
