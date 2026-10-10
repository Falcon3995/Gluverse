#!/usr/bin/env python3
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5050").rstrip("/")
STATE_FILE = os.environ.get("PROOF_STATE_FILE", "/tmp/gluverse-production-proof.json")


class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def csrf(self):
        for cookie in self.cookies:
            if cookie.name == "gluverse_csrf":
                return cookie.value
        return ""

    def request(self, path, method="GET", body=None):
        headers = {"Content-Type": "application/json"}
        if method not in {"GET", "HEAD", "OPTIONS"} and self.csrf():
            headers["X-CSRF-Token"] = self.csrf()
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
    if expected != actual:
        print(f"FAIL {label}: expected {expected}, got {actual}")
        if payload is not None:
            print(json.dumps(payload, indent=2, sort_keys=True))
        sys.exit(1)
    print(f"PASS {label}")


def register_or_login(session, username, password):
    status, payload = session.request("/api/auth/register", "POST", {"username": username, "password": password})
    if status == 409:
        status, payload = session.request("/api/auth/login", "POST", {"username": username, "password": password})
    expect(f"auth {username}", 200, status, payload)
    return payload["user"]["id"]


def main():
    suffix = os.environ.get("PROOF_SUFFIX") or str(int(time.time()))
    password = os.environ.get("PROOF_PASSWORD", "ProofTest!234")
    user_a = f"proof_a_{suffix}"
    user_b = f"proof_b_{suffix}"
    a = Session()
    b = Session()

    user_a_id = register_or_login(a, user_a, password)
    user_b_id = register_or_login(b, user_b, password)

    status, payload = a.request(f"/api/glucose/{user_a_id}", "POST", {"value": 128, "source": "manual", "timestamp": "2026-07-12T05:00:00+00:00"})
    expect("user A glucose create", 201, status, payload)
    status, payload = a.request(f"/api/meals/{user_a_id}", "POST", {"name": "Proof Meal", "carbs": 30, "protein": 12, "fat": 8, "calories": 320})
    expect("user A meal create", 201, status, payload)
    status, payload = a.request(f"/api/insulin/{user_a_id}", "POST", {"insulin_type": "bolus", "units": 2.0})
    expect("user A insulin create", 201, status, payload)
    status, payload = a.request(f"/api/emergency/contacts/{user_a_id}", "PUT", {"contacts": [{"name": "Proof Contact", "phone": "555-0100", "relationship": "Caregiver"}]})
    expect("user A emergency contact save", 200, status, payload)
    status, payload = a.request("/api/community/posts", "POST", {"content": "Production proof community post."})
    expect("user A community post", 201, status, payload)
    status, payload = a.request(f"/api/shop/requests/{user_a_id}", "POST", {"item_id": "low-snack-kit", "quantity": 1, "notes": "Proof supply request"})
    expect("user A shop request", 200, status, payload)

    status, payload = b.request(f"/api/glucose/latest/{user_a_id}")
    expect("user B cannot read user A glucose", 403, status, payload)
    status, payload = b.request(f"/api/meals/{user_a_id}", "POST", {"name": "Bad Cross Write"})
    expect("user B cannot write user A meal", 403, status, payload)

    status, payload = a.request(f"/api/glucose/latest/{user_a_id}")
    expect("user A latest glucose readable", 200, status, payload)
    status, payload = a.request(f"/api/shop/requests/{user_a_id}")
    expect("user A shop requests readable", 200, status, payload)

    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump({
            "username": user_a,
            "password": password,
            "user_id": user_a_id,
            "other_username": user_b,
            "other_user_id": user_b_id,
        }, handle)
    print(f"STATE {STATE_FILE}")


if __name__ == "__main__":
    main()
