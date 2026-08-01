#!/usr/bin/env bash
# Backup dữ liệu thật của minio (bucket, object, user, policy...) nằm trong
# volume minio_data, để copy sang máy mới cùng với offline/minio.tar.gz
# (image, chỉ chứa config chỉnh tay trong container).
#
# Ghi ra offline/minio-volume.tar.gz. Chạy trên máy nguồn.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline"
mkdir -p "$OUT"

VOLUME="${MINIO_VOLUME:-spl20_minio_data}"
SERVICE="${MINIO_SERVICE:-minio}"

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  echo "Không tìm thấy volume $VOLUME (set MINIO_VOLUME=... nếu tên project khác)" >&2
  exit 1
fi

CID="$(docker compose -f "$ROOT/docker-compose.yaml" ps -q "$SERVICE" 2>/dev/null || true)"
WAS_RUNNING=false
if [ -n "$CID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$CID" 2>/dev/null)" = "true" ]; then
  WAS_RUNNING=true
  echo "Dừng service $SERVICE để backup dữ liệu nhất quán..." >&2
  docker compose -f "$ROOT/docker-compose.yaml" stop "$SERVICE"
fi

docker run --rm \
  -v "$VOLUME":/data:ro \
  -v "$OUT":/backup \
  alpine sh -c "cd /data && tar czf /backup/minio-volume.tar.gz ."

if [ "$WAS_RUNNING" = true ]; then
  echo "Khởi động lại $SERVICE..." >&2
  docker compose -f "$ROOT/docker-compose.yaml" start "$SERVICE"
fi

echo "Xong → $OUT/minio-volume.tar.gz" >&2
ls -lh "$OUT/minio-volume.tar.gz" >&2
