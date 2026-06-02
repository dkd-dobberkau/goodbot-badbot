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

# When the compose's image tag actually changes (which is our normal flow
# because the tag is the git short SHA), Mittwald already restarts the
# service as part of stack deploy. We just need to wait for that to settle.
# Only force a manual recreate if the stack didn't pick up the change on its
# own — e.g. when redeploying the same TAG.
TARGET_IMAGE="${IMAGE}:${TAG}"
echo "  waiting for ${TARGET_IMAGE} to become live..."
STATE=""
for i in $(seq 1 60); do
  STATE=$(mw container list --project-id "${PROJECT_ID}" --output json 2>/dev/null \
    | python3 -c "
import sys, json
c = json.load(sys.stdin)[0]
print(c['deployedState']['image'], c['status'])
" 2>/dev/null || echo "")
  [[ "${STATE}" == "${TARGET_IMAGE} running" ]] && break
  sleep 2
done

if [[ "${STATE}" != "${TARGET_IMAGE} running" ]]; then
  echo "  stack deploy did not switch to ${TARGET_IMAGE}; forcing recreate"
  CID=$(mw container list --project-id "${PROJECT_ID}" --output json \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["shortId"])')
  for attempt in 1 2 3; do
    if mw container recreate "${CID}" --project-id "${PROJECT_ID}" --force; then
      break
    fi
    (( attempt < 3 )) || { echo "ERROR: recreate failed after 3 attempts" >&2; exit 1; }
    echo "  recreate attempt ${attempt} failed, retrying in $((attempt * 5))s..."
    sleep $((attempt * 5))
  done
fi

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
  CID_FOR_LOGS=$(mw container list --project-id "${PROJECT_ID}" --output json \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["shortId"])')
  mw container logs "${CID_FOR_LOGS}" --project-id "${PROJECT_ID}" --tail 30 || true
  exit 1
fi

echo "──────────────────────────────────────────────────"
echo "  Live: https://goodbot-badbot.com"
echo "  Image: ${IMAGE}:${TAG}"
echo "──────────────────────────────────────────────────"
