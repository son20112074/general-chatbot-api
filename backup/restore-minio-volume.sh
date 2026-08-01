#!/usr/bin/env bash
# Restore dữ liệu minio (bucket, object, user, policy...) từ
# offline/minio-volume.tar.gz vào volume minio_data trên máy mới.
#
# Chạy TRƯỚC khi `docker compose up minio` (hoặc sau khi đã stop minio),
# để volume có dữ liệu trước khi minio server khởi động.

set -euo pipefail

IN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline/minio-volume.tar.gz"
VOLUME="${MINIO_VOLUME:-spl20_minio_data}"
FORCE="${FORCE:-false}"

if [ ! -f "$IN" ]; then
  echo "Không tìm thấy $IN — chạy backup-minio-volume.sh trên máy nguồn trước" >&2
  exit 1
fi

docker volume create "$VOLUME" >/dev/null

NOT_EMPTY="$(docker run --rm -v "$VOLUME":/data alpine sh -c 'ls -A /data 2>/dev/null | head -1')"
if [ -n "$NOT_EMPTY" ] && [ "$FORCE" != "true" ]; then
  echo "Volume $VOLUME đã có dữ liệu. Restore sẽ ghi đè/trộn lẫn với dữ liệu cũ." >&2
  read -r -p "Tiếp tục? [y/N] " ans </dev/tty
  case "$ans" in
    y|Y) ;;
    *) echo "Huỷ." >&2; exit 1 ;;
  esac
fi

docker run --rm \
  -v "$VOLUME":/data \
  -v "$(dirname "$IN")":/backup \
  alpine sh -c "cd /data && tar xzf /backup/minio-volume.tar.gz"

echo "Đã restore dữ liệu vào volume $VOLUME" >&2
