#!/usr/bin/env bash
# Bundle image cho vector-db/docker-compose.yml (Milvus stack) để mang sang máy
# khác cài offline.
#
# Đọc vào thư mục offline/ trong vector-db/.
#
# Mapping service → image:
#
# etcd       → quay.io/coreos/etcd:v3.5.25
# minio      → minio/minio:RELEASE.2024-12-18T13-15-44Z
# standalone → milvusdb/milvus:v2.6.13
# attu       → zilliz/attu:v2.4

set -euo pipefail

OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline"
mkdir -p "$OUT"

docker save quay.io/coreos/etcd:v3.5.25 | gzip -9 -c >"$OUT/etcd.tar.gz"

docker save minio/minio:RELEASE.2024-12-18T13-15-44Z | gzip -9 -c >"$OUT/minio.tar.gz"

docker save milvusdb/milvus:v2.6.13 | gzip -9 -c >"$OUT/standalone.tar.gz"

docker save zilliz/attu:v2.4 | gzip -9 -c >"$OUT/attu.tar.gz"

echo "Xong → $OUT" >&2
ls -lh "$OUT" >&2
