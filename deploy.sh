#!/usr/bin/env bash
#
# Build, push, and deploy goodbot-badbot to Mittwald container hosting.
#
# Usage:
#   ./deploy.sh              # tags as <short-sha> (+ latest)
#   ./deploy.sh v0.2.0       # tags as v0.2.0 (+ latest)
#
# Requires: docker (buildx), gh (authed), mw (authed)

set -euo pipefail

IMAGE="ghcr.io/dkd-dobberkau/goodbot-badbot"
STACK_ID="55f2a30c-fc87-4c9f-8797-706c3eb4f24a"
PROJECT_ID="p-ckgly6"
HEALTH_URL="https://goodbot-badbot.com/api/stats"

# ── tag ──────────────────────────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
  TAG="$1"
else
  if git rev-parse --git-dir >/dev/null 2>&1; then
    TAG="$(git rev-parse --short HEAD)"
  else
    TAG="$(date +%Y%m%d-%H%M%S)"
  fi
fi

echo "──────────────────────────────────────────────────"
echo "  Deploying ${IMAGE}:${TAG}"
echo "──────────────────────────────────────────────────"

# ── pre-flight ───────────────────────────────────────────────────────────────
command -v docker >/dev/null || { echo "ERROR: docker not found"; exit 1; }
command -v gh     >/dev/null || { echo "ERROR: gh not found";     exit 1; }
command -v mw     >/dev/null || { echo "ERROR: mw not found";     exit 1; }

# Ensure ghcr.io login is fresh
echo "[1/4] Login to ghcr.io"
gh auth token | docker login ghcr.io -u dkd-dobberkau --password-stdin >/dev/null

# ── build + push ─────────────────────────────────────────────────────────────
echo "[2/4] Build linux/amd64 and push (${TAG} + latest)"
docker buildx build \
  --platform linux/amd64 \
  -t "${IMAGE}:${TAG}" \
  -t "${IMAGE}:latest" \
  --push .

# ── deploy ───────────────────────────────────────────────────────────────────
echo "[3/4] Deploy stack to Mittwald and recreate container"
ENV_FILE="$(mktemp -t deploy.env.XXXX)"
trap 'rm -f "${ENV_FILE}"' EXIT
echo "VERSION=${TAG}" > "${ENV_FILE}"
mw stack deploy --stack-id "${STACK_ID}" -c docker-compose.mittwald.yml --env-file "${ENV_FILE}"

# stack deploy alone does not always force a pull/recreate even with a new
# image tag, so we recreate explicitly to make sure the new image is running.
CID=$(mw container list --project-id "${PROJECT_ID}" --output json \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["shortId"])')
mw container recreate "${CID}" --project-id "${PROJECT_ID}" --force

# ── smoke test ───────────────────────────────────────────────────────────────
echo "[4/4] Wait for container to settle, then verify"
sleep 15
HTTP=$(curl -sS -o /dev/null -w "%{http_code}" "${HEALTH_URL}")
if [[ "${HTTP}" != "200" ]]; then
  echo "FAIL: ${HEALTH_URL} returned HTTP ${HTTP}"
  echo "Recent container logs:"
  CID=$(mw container list --project-id "${PROJECT_ID}" --output json | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["shortId"])')
  mw container logs "${CID}" --project-id "${PROJECT_ID}" --tail 30 || true
  exit 1
fi

echo "──────────────────────────────────────────────────"
echo "  Live: https://goodbot-badbot.com"
echo "  Image: ${IMAGE}:${TAG}"
echo "──────────────────────────────────────────────────"
