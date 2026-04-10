# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared GitHub API HTTP client with retry, rate-limit, and auth handling.

All GitHub REST calls in the agent should go through this module.
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import jwt
import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
ORG = os.environ.get("GITHUB_ORG", "opensearch-project")
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
TOKEN_EXPIRY_BUFFER = 300  # seconds before expiry to trigger refresh


def headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


def request(
    method: str,
    url: str,
    token: str,
    json_body: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Make a GitHub API request with retry logic for rate limits and server errors."""
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(
                method, url,
                headers=headers(token),
                json=json_body,
                params=params,
                timeout=30,
            )

            if resp.status_code < 400:
                if resp.status_code == 204:
                    return {"status": "success"}
                return resp.json()

            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset_time = resp.headers.get("x-ratelimit-reset")
                if reset_time:
                    wait = min(max(0, int(reset_time) - int(time.time())) + 1, 60)
                else:
                    wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning("GitHub rate limit hit for %s, waiting %ds", url, wait)
                time.sleep(wait)
                last_error = GitHubAPIError(resp.status_code, resp.text[:500], url)
                continue

            if resp.status_code >= 500:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "GitHub %d on %s (attempt %d/%d), retry in %ds",
                    resp.status_code, url, attempt + 1, MAX_RETRIES, wait,
                )
                last_error = GitHubAPIError(resp.status_code, resp.text[:500], url)
                time.sleep(wait)
                continue

            raise GitHubAPIError(resp.status_code, resp.text[:500], url)

        except requests.RequestException as e:
            wait = INITIAL_BACKOFF * (2 ** attempt)
            logger.error("Request error for %s (attempt %d/%d): %s", url, attempt + 1, MAX_RETRIES, e)
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    if last_error:
        raise last_error
    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {url}")


def get(token: str, path: str, params: Optional[Dict] = None) -> Any:
    """GET helper — path is relative to API_BASE (e.g. '/repos/…')."""
    return request("GET", f"{API_BASE}{path}", token, params=params)


def put(token: str, path: str, json_body: Optional[Dict] = None) -> Any:
    """PUT helper."""
    return request("PUT", f"{API_BASE}{path}", token, json_body=json_body)


def post(token: str, path: str, json_body: Optional[Dict] = None) -> Any:
    """POST helper."""
    return request("POST", f"{API_BASE}{path}", token, json_body=json_body)


class GitHubAPIError(Exception):
    """Error from the GitHub REST API."""

    def __init__(self, status_code: int, message: str, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"GitHub API error {status_code} for {url}: {message}")


# ---------------------------------------------------------------------------
# GitHub App token management
# ---------------------------------------------------------------------------

class TokenManager:
    """Manages GitHub App JWT + installation token lifecycle."""

    def __init__(self, app_id: str, private_key: str, installation_id: str):
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + (10 * 60), "iss": self._app_id}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def needs_refresh(self) -> bool:
        return time.time() >= (self._token_expires_at - TOKEN_EXPIRY_BUFFER)

    def get_token(self) -> Tuple[str, float]:
        """Return (token, expires_at), refreshing if needed."""
        if self._token and time.time() < (self._token_expires_at - TOKEN_EXPIRY_BUFFER):
            return self._token, self._token_expires_at

        token_jwt = self._generate_jwt()
        resp = requests.post(
            f"{API_BASE}/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {token_jwt}", "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["token"]
        expires_str = data.get("expires_at", "")
        if expires_str:
            dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            self._token_expires_at = dt.timestamp()
        else:
            self._token_expires_at = time.time() + 3600

        logger.info("GitHub installation token refreshed")
        return self._token, self._token_expires_at
