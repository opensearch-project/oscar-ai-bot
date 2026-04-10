# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""MCP client that manages the GitHub MCP Server as a subprocess."""

import json
import logging
import os
import shutil
import stat
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from http_client import INITIAL_BACKOFF
from http_client import MAX_RETRIES as MAX_TOOL_RETRIES
from http_client import TokenManager

logger = logging.getLogger(__name__)

BINARY_NAME = "github-mcp-server"
BINARY_SOURCE = os.path.join(os.path.dirname(__file__), "bin", BINARY_NAME)
BINARY_PATH = f"/tmp/{BINARY_NAME}"


class MCPClient:
    """Manages a GitHub MCP Server subprocess and communicates via JSON-RPC over stdio."""

    def __init__(self, app_id: str, private_key: str, installation_id: str):
        self._tokens = TokenManager(app_id, private_key, installation_id)
        self._process: Optional[subprocess.Popen] = None
        self._request_id: int = 0
        self._lock = threading.Lock()

    # -------------------------------------------------------------- process

    @staticmethod
    def _ensure_binary() -> str:
        """Copy binary to /tmp if needed and make executable."""
        if not os.path.exists(BINARY_PATH):
            if not os.path.exists(BINARY_SOURCE):
                raise FileNotFoundError(
                    f"MCP server binary not found at {BINARY_SOURCE}. "
                    "Run scripts/build-github-mcp-server.sh before deploying."
                )
            shutil.copy2(BINARY_SOURCE, BINARY_PATH)
            os.chmod(BINARY_PATH, os.stat(BINARY_PATH).st_mode | stat.S_IEXEC)
            logger.info("Copied MCP server binary to %s", BINARY_PATH)
        return BINARY_PATH

    def _is_process_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _token_needs_refresh(self) -> bool:
        return self._tokens.needs_refresh()

    def _stop_process(self) -> None:
        """Terminate the subprocess if running."""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
                self._process.wait(timeout=5)
            finally:
                self._process = None
            logger.info("MCP server process stopped")

    def _start_process(self) -> None:
        """Spawn the MCP server subprocess and perform initialization handshake."""
        binary = self._ensure_binary()
        token, _ = self._tokens.get_token()

        toolsets = os.environ.get(
            "MCP_TOOLSETS",
            "repos,issues,pull_requests,actions,code_security,labels,context",
        )
        read_only = os.environ.get("MCP_READ_ONLY", "true").lower() == "true"

        cmd = [binary, "stdio", "--toolsets", toolsets]
        if read_only:
            cmd.append("--read-only")

        env = {
            "GITHUB_PERSONAL_ACCESS_TOKEN": token,
            "HOME": "/tmp",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Drain stderr to logger in background thread
        stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        stderr_thread.start()

        # MCP initialization handshake
        self._request_id = 0
        init_result = self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "oscar-github-agent", "version": "1.0"},
        })
        logger.info(
            "MCP server initialized: %s",
            init_result.get("result", {}).get("serverInfo", {}),
        )

        # Send initialized notification (no id, no response expected)
        self._write_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        logger.info("MCP server ready")

    def _drain_stderr(self) -> None:
        """Read stderr from subprocess and forward to logger."""
        try:
            for line in self._process.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.debug("MCP stderr: %s", text)
        except Exception:
            pass

    def _ensure_process(self) -> None:
        """Ensure the MCP server subprocess is running with a valid token."""
        with self._lock:
            if self._is_process_alive() and not self._token_needs_refresh():
                return

            if self._is_process_alive():
                logger.info("Token nearing expiry, restarting MCP server")
                self._stop_process()

            self._start_process()

    # --------------------------------------------------------------- JSON-RPC

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _write_message(self, message: Dict) -> None:
        """Write a JSON-RPC message to the subprocess stdin."""
        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        self._process.stdin.flush()

    def _read_response(self, request_id: int) -> Dict:
        """Read a JSON-RPC response matching the given request ID."""
        while True:
            line = self._process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server process terminated unexpectedly")
            line = line.decode("utf-8").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Non-JSON output from MCP server: %s", line[:200])
                continue
            # Skip notifications (no id field)
            if "id" not in msg:
                continue
            if msg.get("id") == request_id:
                return msg
            logger.warning("Unexpected response id %s (expected %s)", msg.get("id"), request_id)

    def _send_request(self, method: str, params: Any) -> Dict:
        """Send a JSON-RPC request and return the response."""
        req_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        self._write_message(message)
        return self._read_response(req_id)

    # ----------------------------------------------------------------- public

    def get_token(self) -> str:
        """Get a valid installation access token for direct GitHub API calls."""
        token, _ = self._tokens.get_token()
        return token

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call an MCP tool and return the result text.

        Retries on server errors (5xx patterns) and rate limit errors with
        exponential backoff. Non-retryable errors are raised immediately.
        """
        last_error = None

        for attempt in range(MAX_TOOL_RETRIES):
            try:
                self._ensure_process()

                response = self._send_request("tools/call", {
                    "name": tool_name,
                    "arguments": arguments,
                })

                if "error" in response:
                    error = response["error"]
                    error_msg = error.get("message", "")
                    error_code = error.get("code", "unknown")

                    # Check if this is a retryable error (server error or rate limit)
                    if self._is_retryable_error(error_msg, error_code):
                        wait = INITIAL_BACKOFF * (2 ** attempt)
                        logger.error(
                            "MCP retryable error on '%s' (attempt %d/%d, code=%s): %s. "
                            "Retrying in %ds.",
                            tool_name, attempt + 1, MAX_TOOL_RETRIES,
                            error_code, error_msg[:300], wait,
                        )
                        last_error = RuntimeError(
                            f"MCP error ({error_code}): {error_msg}"
                        )
                        time.sleep(wait)
                        continue

                    # Non-retryable MCP error
                    logger.error(
                        "MCP non-retryable error on '%s' (code=%s): %s",
                        tool_name, error_code, error_msg[:500],
                    )
                    raise RuntimeError(f"MCP error ({error_code}): {error_msg}")

                result = response.get("result", {})
                if result.get("isError"):
                    texts = [
                        c.get("text", "")
                        for c in result.get("content", [])
                        if c.get("type") == "text"
                    ]
                    error_text = " ".join(texts)

                    if self._is_retryable_error(error_text):
                        wait = INITIAL_BACKOFF * (2 ** attempt)
                        logger.error(
                            "MCP tool retryable error on '%s' (attempt %d/%d): %s. "
                            "Retrying in %ds.",
                            tool_name, attempt + 1, MAX_TOOL_RETRIES,
                            error_text[:300], wait,
                        )
                        last_error = RuntimeError("MCP tool error: " + error_text)
                        time.sleep(wait)
                        continue

                    logger.error(
                        "MCP tool error on '%s': %s", tool_name, error_text[:500],
                    )
                    raise RuntimeError("MCP tool error: " + error_text)

                # Success — concatenate all text content blocks
                texts = [
                    c.get("text", "")
                    for c in result.get("content", [])
                    if c.get("type") == "text"
                ]
                return "\n".join(texts)

            except RuntimeError:
                raise
            except Exception as e:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.error(
                    "MCP unexpected error on '%s' (attempt %d/%d): %s. Retrying in %ds.",
                    tool_name, attempt + 1, MAX_TOOL_RETRIES, e, wait,
                )
                last_error = e
                if attempt < MAX_TOOL_RETRIES - 1:
                    # Process may have died; force restart on next attempt
                    self._stop_process()
                    time.sleep(wait)

        # All retries exhausted
        logger.error(
            "All %d retry attempts exhausted for MCP tool '%s'. Last error: %s",
            MAX_TOOL_RETRIES, tool_name, last_error,
        )
        raise last_error or RuntimeError(
            f"All {MAX_TOOL_RETRIES} retry attempts failed for tool '{tool_name}'"
        )

    @staticmethod
    def _is_retryable_error(error_text: str, error_code: Any = None) -> bool:
        """Determine if an MCP error is retryable (rate limit or server error)."""
        text_lower = error_text.lower()
        # Rate limit indicators
        if "rate limit" in text_lower or "403" in text_lower:
            return True
        # Server error indicators
        if any(code in text_lower for code in ("500", "502", "503", "504")):
            return True
        if "server error" in text_lower or "internal error" in text_lower:
            return True
        return False

    def close(self) -> None:
        """Shut down the MCP server subprocess."""
        self._stop_process()
