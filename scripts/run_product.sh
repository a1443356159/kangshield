#!/usr/bin/env bash
# Continuous product service: in-memory screening, local dashboard and cloud replay.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
. secrets/ys7.env
set +a

: "${YS7_APP_KEY:?set YS7_APP_KEY in secrets/ys7.env}"
: "${YS7_APP_SECRET:?set YS7_APP_SECRET in secrets/ys7.env}"
: "${KANG_DEVICE_SERIAL:?set KANG_DEVICE_SERIAL in secrets/ys7.env}"
: "${KANG_ELDER_REF:?set KANG_ELDER_REF in secrets/ys7.env}"
: "${KANG_DEVICE_REF:?set KANG_DEVICE_REF in secrets/ys7.env}"

exec .venv/bin/kangshield-info serve-product \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF" \
  --host 127.0.0.1 \
  --port 8765 \
  --continuous \
  --local-anomaly-archive \
  --edge-provider ezviz \
  --edge-device-serial-env KANG_DEVICE_SERIAL \
  --cloud-playback-provider ezviz \
  --store-root data/processed/longitudinal
