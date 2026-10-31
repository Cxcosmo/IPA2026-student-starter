import json
import os
import shutil
import subprocess
from pathlib import Path

from app.backends.common import (
    classify_error,
    error,
    ok,
    router_credentials,
    split_cidr,
)


ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
PLAYBOOK = ANSIBLE_DIR / "apply_interface.yml"
INVENTORY = ANSIBLE_DIR / "inventory.ini"

PLAYBOOK_TIMEOUT = 120

UNREACHABLE_RC = 4

AUTHENTICATION_MARKERS = (
    "authentication failed",
    "permission denied",
    "bad password",
    "incorrect password",
    "authentication failure",
)


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    if run_playbook is None:
        run_playbook = _default_run_playbook

    try:
        variables = build_variables(router, desired_interface)
    except (KeyError, ValueError):
        return error("backend_failed")

    try:
        run_playbook(variables)
    except Exception as exception:
        return error(classify_error(exception))

    return ok("applied")


def build_variables(router, desired_interface):
    """Convert the normalized desired state into playbook variables."""
    address, netmask = split_cidr(desired_interface["ipv4"])

    return {
        "router": router,
        "interface_name": desired_interface["name"],
        "description": desired_interface["description"],
        "ipv4_address": address,
        "netmask": netmask,
        "shutdown": desired_interface.get("admin_state") == "down",
    }


def _default_run_playbook(variables):
    """Run the apply playbook with ansible-playbook."""
    executable = shutil.which("ansible-playbook")

    if executable is None:
        raise RuntimeError("ansible-playbook is not installed")

    user, password = router_credentials()

    extra_vars = dict(variables)
    extra_vars["router_user"] = user
    extra_vars["router_pass"] = password

    environment = dict(os.environ)
    environment["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    environment["ANSIBLE_RETRY_FILES_ENABLED"] = "False"

    completed = subprocess.run(
        [
            executable,
            "-i",
            str(INVENTORY),
            str(PLAYBOOK),
            "--extra-vars",
            json.dumps(extra_vars),
        ],
        capture_output=True,
        text=True,
        timeout=PLAYBOOK_TIMEOUT,
        env=environment,
        cwd=str(ANSIBLE_DIR),
    )

    if completed.returncode == 0:
        return

    output = f"{completed.stdout}\n{completed.stderr}".lower()

    # The runner raises built-in exceptions so apply_interface can use the
    # one shared error mapping for both the real and the injected path.
    if any(marker in output for marker in AUTHENTICATION_MARKERS):
        raise PermissionError(output)

    if completed.returncode == UNREACHABLE_RC or "unreachable" in output:
        raise ConnectionError(output)

    raise RuntimeError(output)
