"""Part 4 student implementation."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

MIN_BODY_BYTES = 1
MAX_BODY_BYTES = 1_000_000

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

HEALTH_RESPONSE = {"status": "ok", "result": "healthy"}
ACCEPTED_RESPONSE = {"status": "ok", "result": "accepted"}
INVALID_EVENT_RESPONSE = {"status": "error", "result": "invalid_event"}
NOT_FOUND_RESPONSE = {"status": "error", "result": "not_found"}

logger = logging.getLogger(__name__)


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor if processor is not None else process_request

    def handle_event(self, event):
        """Process one messages/created event and reply in its own room."""
        if not isinstance(event, dict):
            return None

        if event.get("resource") != "messages":
            return None

        if event.get("event") != "created":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None

        message_id = data.get("id")
        if not message_id:
            return None

        # Skip the bot's own messages before the lookup when the event
        # already identifies the author, and again after fetching the
        # message, so replies cannot trigger new events.
        if data.get("personId") == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)

        if not isinstance(message, dict):
            return None

        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        mentioned_people = message.get("mentionedPeople") or []
        files = message.get("files") or []

        response = self._respond_to(mentioned_people, files)

        if room_id:
            self.client.send_message(room_id, json.dumps(response))

        return response

    def _respond_to(self, mentioned_people, files):
        if len(files) > 1:
            return {"status": "error", "result": "multiple_attachments"}

        if not files:
            return self.processor(mentioned_people, None, self.bot_person_id)

        try:
            content = self.client.download_file(files[0])
        except Exception:
            logger.exception("Could not download the Webex attachment")
            return {"status": "error", "result": "backend_failed"}

        # The temporary directory is removed on exit, so the YAML file is
        # cleaned up even when processing raises.
        with TemporaryDirectory() as directory:
            path = Path(directory) / "request.yaml"
            path.write_bytes(content)

            return self.processor(
                mentioned_people,
                path,
                self.bot_person_id,
            )


def make_http_handler(submit_event):
    """Build the HTTP handler class used by the webhook server."""

    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self._route() == "/health":
                self._reply(200, HEALTH_RESPONSE)
            else:
                self._reply(404, NOT_FOUND_RESPONSE)

        def do_POST(self):
            if self._route() != "/webhook":
                self._reply(404, NOT_FOUND_RESPONSE)
                return

            event = self._read_event()

            if event is None:
                self._reply(400, INVALID_EVENT_RESPONSE)
                return

            # Acknowledge receipt immediately; the router work and the
            # Webex reply happen in the background.
            submit_event(event)
            self._reply(200, ACCEPTED_RESPONSE)

        def _read_event(self):
            try:
                length = int(self.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                return None

            if not MIN_BODY_BYTES <= length <= MAX_BODY_BYTES:
                return None

            try:
                event = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                return None

            return event if isinstance(event, dict) else None

        def _route(self):
            return self.path.split("?", 1)[0].rstrip("/") or "/"

        def _reply(self, status, payload):
            body = json.dumps(payload).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            logger.debug("%s - %s", self.address_string(), format % args)

    return WebhookHTTPHandler


def main():
    logging.basicConfig(level=logging.INFO)

    client = WebexClient()
    bot_person_id = client.get_me()["id"]

    handler = WebexEventHandler(client, bot_person_id)

    logger.info("Bot personId %s, Webex API %s", bot_person_id, WEBEX_API_BASE)

    # One worker keeps router operations sequential so two requests cannot
    # change the same interface at the same time.
    executor = ThreadPoolExecutor(max_workers=1)

    def submit_event(event):
        executor.submit(_process_event, handler, event)

    host = os.environ.get("WEBHOOK_HOST", DEFAULT_HOST)
    port = int(os.environ.get("WEBHOOK_PORT", DEFAULT_PORT))

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))

    logger.info("Listening on %s:%s", host, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        executor.shutdown(wait=True)


def _process_event(handler, event):
    try:
        handler.handle_event(event)
    except Exception:
        logger.exception("Could not handle the Webex event")


if __name__ == "__main__":
    main()
