"""Persist daily send reservations before interacting with the Send control."""
import base64
import hashlib
import json
import os
from pathlib import Path

import requests


class DeliveryState:
    def __init__(self, day):
        self.day = day
        self.repo = os.getenv("GITHUB_REPOSITORY")
        self.token = os.getenv("DOUYIN_STATE_TOKEN")
        self.path = Path(__file__).parent / ".delivery-state.json"
        if self.repo and not self.token:
            raise RuntimeError("Missing delivery state token")

    def _load(self):
        if not self.repo:
            return (json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}), None
        response = requests.get(
            f"https://api.github.com/repos/{self.repo}/contents/.github/delivery-state.json",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
            params={"ref": "douyin-state"}, timeout=20,
        )
        if response.status_code == 404:
            return {}, None
        if response.status_code != 200:
            raise RuntimeError("Cannot read delivery state")
        data = response.json()
        return json.loads(base64.b64decode(data["content"])), data["sha"]

    def _key(self, recipient):
        return self.day + "/" + hashlib.sha256(recipient.encode("utf-8")).hexdigest()

    def was_attempted(self, recipient):
        entries, _ = self._load()
        return self._key(recipient) in entries

    def reserve(self, recipient):
        for _ in range(3):
            entries, sha = self._load()
            key = self._key(recipient)
            if key in entries:
                return False
            entries[key] = "attempted"
            content = json.dumps(entries, sort_keys=True)
            if not self.repo:
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(content, encoding="utf-8")
                temporary.replace(self.path)
                return True
            payload = {
                "message": "Reserve daily Douyin delivery",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": "douyin-state",
            }
            if sha:
                payload["sha"] = sha
            response = requests.put(
                f"https://api.github.com/repos/{self.repo}/contents/.github/delivery-state.json",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
                json=payload, timeout=20,
            )
            if response.status_code in (200, 201):
                return True
            if response.status_code not in (409, 422):
                raise RuntimeError("Cannot persist delivery reservation")
        raise RuntimeError("Delivery state changed concurrently")
