"""Part 4 student implementation."""

import os

import requests

WEBEX_API_BASE = 'https://webexapis.com/v1'

REQUEST_TIMEOUT = 10


class WebexClient:
    def __init__(self, token=None, session=None):
        if token is None:
            token = os.environ.get("WEBEX_BOT_TOKEN")

        if not token:
            raise PermissionError(
                "WEBEX_BOT_TOKEN must be set in the environment"
            )

        self.token = token
        self.session = session if session is not None else requests.Session()

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_me(self):
        """Return the bot's own identity, including its personId."""
        response = self.session.get(
            f"{WEBEX_API_BASE}/people/me",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        return response.json()

    def get_message(self, message_id):
        response = self.session.get(
            f"{WEBEX_API_BASE}/messages/{message_id}",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        return response.json()

    def download_file(self, file_url):
        response = self.session.get(
            file_url,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        return response.content

    def send_message(self, room_id, text):
        response = self.session.post(
            f"{WEBEX_API_BASE}/messages",
            headers=self.headers,
            json={"roomId": room_id, "text": text},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        return response.json()
