#!/usr/bin/env bash
# Download and verify the GitHub MCP Server binary for Lambda packaging.
# Reads URL and expected SHA256 from agents/github/mcp-server.json.
#
# Usage: ./scripts/download-mcp-server.sh
#
set -euo pipefail

MANIFEST="agents/github/mcp-server.json"
OUTPUT_DIR="agents/github/lambda/bin"

if [ ! -f "${MANIFEST}" ]; then
  echo "FATAL: Manifest not found at ${MANIFEST}" >&2
  exit 1
fi

URL=$(jq -r '.url' "${MANIFEST}")
EXPECTED_SHA=$(jq -r '.sha256' "${MANIFEST}")

echo "Downloading MCP server from: ${URL}"
mkdir -p "${OUTPUT_DIR}"
curl -sfL "${URL}" -o /tmp/mcp-server.tar.gz
tar xzf /tmp/mcp-server.tar.gz -C "${OUTPUT_DIR}" github-mcp-server
rm -f /tmp/mcp-server.tar.gz

ACTUAL_SHA=$(sha256sum "${OUTPUT_DIR}/github-mcp-server" | awk '{print $1}')
if [ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]; then
  echo "FATAL: SHA256 mismatch!" >&2
  echo "  Expected: ${EXPECTED_SHA}" >&2
  echo "  Actual:   ${ACTUAL_SHA}" >&2
  exit 1
fi

chmod +x "${OUTPUT_DIR}/github-mcp-server"
echo "OK: github-mcp-server verified (sha256: ${ACTUAL_SHA})"
ls -lh "${OUTPUT_DIR}/github-mcp-server"
