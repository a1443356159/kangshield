#!/usr/bin/env bash
# Scheduled camera capture round.
#
# - reads EZVIZ credentials and KANG_CAPTURE_DEVICES from
#   secrets/ys7.env (0600, gitignored)
# - fetches a fresh FLV endpoint per device, warms the cloud stream, then
#   runs a bounded capture-stream with built-in media probe
# - appends one value-free status line per device to
#   logs/scheduled_capture/status.jsonl
# - deletes stream-capture.mkv artifacts older than RETENTION_DAYS
#
# Override DURATION_S for a short smoke run: DURATION_S=10 scripts/scheduled_capture.sh
set -u
cd "$(dirname "$0")/.."

DURATION_S="${DURATION_S:-60}"
MINIMUM_S="${MINIMUM_S:-50}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STATUS_LOG="logs/scheduled_capture/status.jsonl"

mkdir -p logs/scheduled_capture
set -a
# shellcheck disable=SC1091
. secrets/ys7.env
set +a

if [ -z "${KANG_CAPTURE_DEVICES:-}" ]; then
  echo "KANG_CAPTURE_DEVICES must list serial:device_ref entries" >&2
  exit 2
fi

for device in $KANG_CAPTURE_DEVICES; do
  serial="${device%%:*}"
  ref="${device##*:}"
  endpoint=$(.venv/bin/python scripts/ezviz_live_endpoint.py "$serial" 2>>logs/scheduled_capture/cron.log)
  if [ -z "$endpoint" ]; then
    .venv/bin/python - "$ref" <<'PY' >>"$STATUS_LOG"
import json, sys
from datetime import datetime, timezone
print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                  "device_ref": sys.argv[1], "status": "endpoint_failed"}))
PY
    continue
  fi
  # Cold cloud streams answer 404 to ffmpeg; warm once first.
  curl -s -o /dev/null --max-time 8 -r 0-1023 "$endpoint" 2>/dev/null || true

  output=$(KANG_STREAM_ENDPOINT="$endpoint" .venv/bin/kangshield-info capture-stream \
    --evidence-level E2 \
    --source-type network_stream \
    --device-ref "$ref" \
    --duration-s "$DURATION_S" \
    --minimum-duration-s "$MINIMUM_S" 2>&1)
  CAPTURE_OUTPUT="$output" .venv/bin/python - "$ref" <<'PY' >>"$STATUS_LOG"
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import av
import numpy as np
from av.audio.resampler import AudioResampler

device_ref = sys.argv[1]
record = {"ts": datetime.now(timezone.utc).isoformat(), "device_ref": device_ref}
try:
    report = json.loads(os.environ["CAPTURE_OUTPUT"])
except json.JSONDecodeError:
    record["status"] = "capture_failed"
else:
    record.update(
        status="ready" if report.get("capture_artifact_ready") else "not_ready",
        run_id=report.get("run_id"),
        media_span_ms=report.get("captured_media_span_ms"),
        video_packets=report.get("video_packet_count"),
        audio_packets=report.get("audio_packet_count"),
        multimodal_ready=report.get("same_container_multimodal_ready"),
    )
    artifact = Path(report["run_dir"]) / report["capture_artifact"]
    try:
        container = av.open(str(artifact))
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = AudioResampler(format="flt", layout="mono", rate=16000)
        chunks = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
        samples = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        record["audio_rms"] = round(float(np.sqrt(np.mean(samples**2))), 6)
    except Exception:
        record["audio_rms"] = None
print(json.dumps(record, ensure_ascii=False))
PY
done

find runs -name 'stream-capture.mkv' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
