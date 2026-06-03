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
BASE_URL="https://goodbot-badbot.com"
HEALTH_URL="${BASE_URL}/api/stats"
VERSION_URL="${BASE_URL}/api/version"

# Mittwald stack/project identifiers come from .deploy.env so the public
# repo doesn't ship internal IDs. Sourced before pre-flight so missing
# values fail fast.
if [[ ! -f .deploy.env ]]; then
  echo "ERROR: .deploy.env not found. Copy .deploy.env.example and fill in." >&2
  exit 1
fi
set -a
# shellcheck source=/dev/null
. .deploy.env
set +a
: "${STACK_ID:?STACK_ID missing from .deploy.env}"
: "${PROJECT_ID:?PROJECT_ID missing from .deploy.env}"

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
  --build-arg "GIT_SHA=${TAG}" \
  -t "${IMAGE}:${TAG}" \
  -t "${IMAGE}:latest" \
  --push .

# ── deploy ───────────────────────────────────────────────────────────────────
echo "[3/4] Deploy stack to Mittwald and recreate container"

ENV_FILE="$(mktemp -t deploy.env.XXXX)"
trap 'rm -f "${ENV_FILE}"' EXIT
{
  echo "VERSION=${TAG}"
  cat .deploy.env
} > "${ENV_FILE}"

mw stack deploy --stack-id "${STACK_ID}" -c docker-compose.mittwald.yml --env-file "${ENV_FILE}"

# Probe the running code via /api/version rather than Mittwald's
# deployedState.image — the latter has lied to us multiple times,
# reporting the new tag while the container still ran old code. Source
# of truth is what the process actually serves.
probe_live_version() {
  curl -fsS --max-time 5 "${VERSION_URL}" 2>/dev/null \
    | python3 -c 'import sys, json
try: print(json.load(sys.stdin).get("version", ""))
except Exception: print("")' 2>/dev/null \
    || true
}

wait_for_version() {
  local expected="$1" max_iter="$2" current=""
  for ((i = 0; i < max_iter; i++)); do
    current="$(probe_live_version)"
    if [[ "${current}" == "${expected}" ]]; then
      printf '%s' "${current}"
      return 0
    fi
    sleep 2
  done
  printf '%s' "${current}"
  return 1
}

echo "  waiting for /api/version to report ${TAG}..."
LIVE_VERSION="$(wait_for_version "${TAG}" 30)" || {
  echo "  /api/version reports '${LIVE_VERSION:-<empty>}', expected '${TAG}'; forcing recreate"
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
  echo "  re-probing /api/version after recreate..."
  LIVE_VERSION="$(wait_for_version "${TAG}" 30)" || {
    echo "ERROR: /api/version still reports '${LIVE_VERSION:-<empty>}' after forced recreate" >&2
    exit 1
  }
}
echo "  live version: ${LIVE_VERSION}"

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
