import os

import httpx

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://localhost:8090")

TIMEOUT = 60


def post(path: str, json: dict) -> httpx.Response:
    return httpx.post(f"{APP_URL}{path}", json=json, timeout=TIMEOUT)


def get(path: str, follow_redirects: bool = False) -> httpx.Response:
    return httpx.get(f"{APP_URL}{path}", timeout=TIMEOUT, follow_redirects=follow_redirects)
