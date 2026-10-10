#!/usr/bin/env python3
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5050").rstrip("/")
STATE_FILE = os.environ.get("PROOF_STATE_FILE", "/tmp/gluverse-production-proof.json")


class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def request(self, path, method="GET", body=None):
        headers = {"Content-Type": "application/json"}
        if method not in {"GET", "HEAD", "OPTIONS"}:
            for cookie in self.cookies:
                if cookie.name == "gluverse_csrf":
                    headers["X-CSRF-Token"] = cookie.value
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=15) as response:
                payload = response.read().decode("utf-8")
                return response.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8")
            try:
                parsed = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                parsed = {"raw": payload}
            return exc.code, parsed


def expect(label, expected, actual, payload=None):
    if actual != expected:
        print(f"FAIL {label}: expected {expected}, got {actual}")
        if payload is not None:
            print(json.dumps(payload, indent=2, sort_keys=True))
        sys.exit(1)
    print(f"PASS {label}")


def main():
    with open(STATE_FILE, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    session = Session()
    status, payload = session.request("/api/auth/login", "POST", {"username": state["username"], "password": state["password"]})
    expect("state login", 200, status, payload)
    status, payload = session.request(f"/api/glucose/latest/{state['user_id']}")
    expect("state latest glucose", 200, status, payload)
    if payload.get("value") != 128:
        print(f"FAIL state latest glucose value: expected 128, got {payload.get('value')}")
        sys.exit(1)
    status, payload = session.request(f"/api/shop/requests/{state['user_id']}")
    expect("state shop request", 200, status, payload)
    if not any(item.get("item_id") == "low-snack-kit" for item in payload):
        print("FAIL state shop request: low-snack-kit not found")
        sys.exit(1)
    status, payload = session.request(f"/api/emergency/contacts/{state['user_id']}")
    expect("state emergency contact", 200, status, payload)
    if not any(item.get("name") == "Proof Contact" for item in payload):
        print("FAIL state emergency contact: Proof Contact not found")
        sys.exit(1)
    print("State verification passed")


if __name__ == "__main__":
    main()
