#!/usr/bin/env python3
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
USERNAME = os.environ.get("SMOKE_USERNAME") or f"smoke_{int(time.time())}"
PASSWORD = os.environ.get("SMOKE_PASSWORD") or "SmokeTest!234"
EXPECTED_DEMO_RESET_STATUS = int(os.environ.get("DEMO_RESET_EXPECTED_STATUS", "403"))

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def cookie_value(name):
    for cookie in cookie_jar:
        if cookie.name == name:
            return cookie.value
    return ""


def request(path, method="GET", body=None, headers=None):
    data = None
    req_headers = {"Content-Type": "application/json"}
    if method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = cookie_value("gluverse_csrf")
        if csrf:
            req_headers["X-CSRF-Token"] = csrf
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, bytearray)) else body
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=req_headers, method=method)
    try:
        with opener.open(req, timeout=15) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return exc.code, parsed


def expect(status, actual, label, payload=None):
    if actual != status:
        print(f"FAIL {label}: expected {status}, got {actual}")
        if payload is not None:
            print(json.dumps(payload, indent=2, sort_keys=True))
        sys.exit(1)
    print(f"PASS {label}")


def main():
    status, data = request("/api/health")
    expect(200, status, "health", data)
    status, data = request("/api/ready")
    expect(200, status, "ready", data)

    status, data = request("/api/auth/register", "POST", {"username": USERNAME, "password": PASSWORD})
    if status == 409:
        status, data = request("/api/auth/login", "POST", {"username": USERNAME, "password": PASSWORD})
        expect(200, status, "login existing smoke user", data)
    else:
        expect(200, status, "register", data)

    user_id = data["user"]["id"]
    status, data = request("/api/auth/me")
    expect(200, status, "auth me", data)

    status, data = request(f"/api/glucose/{user_id}", "POST", {"value": 123, "source": "manual", "timestamp": "2026-07-11T00:00:00+00:00"})
    expect(201, status, "create glucose", data)
    status, data = request(f"/api/glucose/latest/{user_id}")
    expect(200, status, "latest glucose", data)

    status, data = request(f"/api/meals/{user_id}", "POST", {"name": "Smoke Meal", "carbs": 25, "protein": 10, "fat": 5, "calories": 250})
    expect(201, status, "create meal", data)

    status, data = request(f"/api/insulin/{user_id}", "POST", {"insulin_type": "bolus", "units": 2.5})
    expect(201, status, "create insulin", data)

    status, data = request(f"/api/settings/{user_id}")
    expect(200, status, "get settings", data)

    status, data = request(f"/api/settings/{user_id}", "PUT", {
        "profile": {"username": USERNAME, "diabetes_type": "Type 1", "units": "mg/dL", "target_low": 70, "target_high": 180},
        "alert_rules": {"urgent_low": 54, "low": 70, "high": 180, "urgent_high": 250, "stale_minutes": 30, "missed_meal_hours": 6},
        "notification_settings": {"low_glucose_alert": True, "high_glucose_alert": True, "stale_data_alert": True, "missed_meal_alert": False, "email_enabled": False, "sms_enabled": False, "push_enabled": True},
    })
    expect(200, status, "update settings", data)

    status, data = request("/api/community/posts", "POST", {"content": "Smoke test peer-support post."})
    expect(201, status, "create community post", data)

    status, data = request("/api/cgm/sync", "POST", {"username": "demo", "password": "demo"})
    expect(503, status, "disabled cgm integration", data)

    status, data = request("/api/auth/logout", "POST")
    expect(200, status, "logout", data)

    status, data = request("/api/auth/me")
    expect(401, status, "session invalidation", data)

    status, data = request("/api/auth/login", "POST", b"{")
    expect(400, status, "invalid json", data)

    status, data = request("/api/demo/reset", "POST")
    expect(EXPECTED_DEMO_RESET_STATUS, status, "demo reset policy", data)

    state_file = os.environ.get("PERSISTENCE_STATE_FILE")
    if state_file:
        with open(state_file, "w", encoding="utf-8") as handle:
            json.dump({"username": USERNAME, "password": PASSWORD, "user_id": user_id}, handle)

    print("Smoke test passed")


if __name__ == "__main__":
    main()
