"""Part 4 student implementation."""

import yaml

from app.core import validate_request

from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope


def process_request(mentioned_people, attachment_path, bot_person_id):
    """Validate the Webex envelope and YAML, then dispatch to a backend."""
    envelope_error = validate_webex_envelope(
        mentioned_people,
        attachment_path,
        bot_person_id,
    )

    if envelope_error is not None:
        return envelope_error

    try:
        with open(attachment_path, "r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {"status": "error", "result": "invalid_yaml"}

    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}

    validation = validate_request(data)

    if validation["status"] == "error":
        return validation

    return dispatch_request(data)
