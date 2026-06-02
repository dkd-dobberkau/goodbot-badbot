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

if [[ ! -f .deploy.env ]]; then
  echo "ERROR: .deploy.env not found. Copy .deploy.env.example and fill in secrets." >&2
  exit 1
fi

ENV_FILE="$(mktemp -t deploy.env.XXXX)"
trap 'rm -f "${ENV_FILE}"' EXIT
{
  echo "VERSION=${TAG}"
  cat .deploy.env
} > "${ENV_FILE}"

mw stack deploy --stack-id "${STACK_ID}" -c docker-compose.mittwald.yml --env-file "${ENV_FILE}"

# Helpers for the rest of this step.
container_field() {
  # $1 = JSON path expression, e.g. ["shortId"] or ["deployedState"]["image"]
  mw container list --project-id "${PROJECT_ID}" --output json \
    | python3 -c "import sys,json; print(json.load(sys.stdin)[0]$1)"
}

CID=$(container_field '["shortId"]')

# stack deploy alone does not always force a pull/recreate even with a new
# image tag, so we recreate explicitly. Mittwald's API is mid-reconciliation
# right after the deploy call returns; we wait for the pending spec to match
# the image we just pushed, otherwise recreate races against the in-flight
# spec update and can error out.
echo "  waiting for new spec to register..."
for i in $(seq 1 10); do
  PENDING=$(container_field '["pendingState"]["image"]' 2>/dev/null || echo "")
  [[ "${PENDING}" == "${IMAGE}:${TAG}" ]] && break
  sleep 2
done

# Recreate with retry — the API can still return a transient error during the
# first few seconds after a spec change.
for attempt in 1 2 3; do
  if mw container recreate "${CID}" --project-id "${PROJECT_ID}" --force; then
    break
  fi
  # The CLI sometimes prints a stack trace even though the recreate succeeded
  # server-side. Bail out of the retry loop if the deployed image is already
  # on target — we are done either way.
  DEPLOYED=$(container_field '["deployedState"]["image"]' 2>/dev/null || echo "")
  if [[ "${DEPLOYED}" == "${IMAGE}:${TAG}" ]]; then
    echo "  CLI reported an error but container is on target image; continuing"
    break
  fi
  (( attempt < 3 )) || { echo "ERROR: recreate failed after 3 attempts" >&2; exit 1; }
  echo "  recreate attempt ${attempt} failed, retrying in $((attempt * 5))s..."
  sleep $((attempt * 5))
done

# ── smoke test ───────────────────────────────────────────────────────────────
echo "[4/4] Wait for container to settle, then verify"
HTTP=000
for i in $(seq 1 12); do
  sleep 3
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${HEALTH_URL}" 2>/dev/null || echo "000")
  [[ "${HTTP}" == "200" ]] && break
done
if [[ "${HTTP}" != "200" ]]; then
  echo "FAIL: ${HEALTH_URL} returned HTTP ${HTTP} after 36s of retries"
  echo "Recent container logs:"
  mw container logs "${CID}" --project-id "${PROJECT_ID}" --tail 30 || true
  exit 1
fi

echo "──────────────────────────────────────────────────"
echo "  Live: https://goodbot-badbot.com"
echo "  Image: ${IMAGE}:${TAG}"
echo "──────────────────────────────────────────────────"
