#!/usr/bin/env bash
# Load lại các .tar.gz do save_image_vector_db.sh ghi vào offline/.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline"

gunzip -c "$DIR/etcd.tar.gz" | docker load

gunzip -c "$DIR/minio.tar.gz" | docker load

gunzip -c "$DIR/standalone.tar.gz" | docker load

gunzip -c "$DIR/attu.tar.gz" | docker load

echo "Đã load xong mọi image từ $DIR" >&2
