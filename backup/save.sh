#!/usr/bin/env bash
# Bundle image cho 2 file compose:
#   docker-compose.yaml (root) → project spl20-* (đúng khi repo ở thư mục SPL2.0).
#   llm-cluster/docker-compose.yml → image vllm/vllm-openai:custom
#
# Trước khi save: compose build các service có build (docker compose ... build hoặc up một lần).
# Đọc vào thư mục offline/ trong docker-images/.
#
# Mapping service → image (xem và sửa prefix spl20- nếu COMPOSE_PROJECT_NAME khác):

set -euo pipefail

OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline"
mkdir -p "$OUT"

# ─── docker-compose.yaml ───────────────────────────────────
#
# alb                        → nginx:alpine
# general-chatbot-web        → spl20-general-chatbot-web
# chatbot-api                → spl20-chatbot-api
# chat-server                → spl20-chat-server
# db                         → postgres:14
# minio                      → minio/minio:latest
# media-service              → spl20-media-service
# graph-extraction-job       → spl20-graph-extraction-job
# topic-classification-job    → spl20-topic-classification-job
# file-processing-job        → spl20-file-processing-job
# omnivoice-tts              → spl20-omnivoice-tts
# vector-db-realtime-ingest → spl20-vector-db-realtime-ingest

docker save nginx:alpine | gzip -9 -c >"$OUT/alb.tar.gz"

docker save spl20-general-chatbot-web | gzip -9 -c >"$OUT/general-chatbot-web.tar.gz"

docker save spl20-chatbot-api | gzip -9 -c >"$OUT/chatbot-api.tar.gz"

docker save spl20-chat-server | gzip -9 -c >"$OUT/chat-server.tar.gz"

docker save postgres:14 | gzip -9 -c >"$OUT/db.tar.gz"

# minio: commit từ container đang chạy (đã chỉnh tay config sau khi start)
# thay vì save image minio/minio:latest gốc từ Docker Hub.
# Lưu ý: docker commit chỉ lấy filesystem của container, KHÔNG lấy dữ liệu
# trong volume minio_data (bucket, user, policy...). Dùng backup-minio-volume.sh
# riêng để backup phần đó.
MINIO_CONTAINER="${MINIO_CONTAINER:-spl20-minio-1}"
if docker inspect "$MINIO_CONTAINER" >/dev/null 2>&1; then
  echo "Commit container $MINIO_CONTAINER → minio/minio:latest" >&2
  docker commit "$MINIO_CONTAINER" minio/minio:latest >/dev/null
else
  echo "Cảnh báo: không thấy container $MINIO_CONTAINER, save nguyên image minio/minio:latest gốc" >&2
fi
docker save minio/minio:latest | gzip -9 -c >"$OUT/minio.tar.gz"

docker save spl20-media-service | gzip -9 -c >"$OUT/media-service.tar.gz"

docker save spl20-graph-extraction-job | gzip -9 -c >"$OUT/graph-extraction-job.tar.gz"

docker save spl20-topic-classification-job | gzip -9 -c >"$OUT/topic-classification-job.tar.gz"

docker save spl20-file-processing-job | gzip -9 -c >"$OUT/file-processing-job.tar.gz"

docker save spl20-omnivoice-tts | gzip -9 -c >"$OUT/omnivoice-tts.tar.gz"

docker save spl20-vector-db-realtime-ingest | gzip -9 -c >"$OUT/vector-db-realtime-ingest.tar.gz"

# ─── llm-cluster/docker-compose.yml ───────────────────────
#
# vllm-server                → vllm/vllm-openai:custom

docker save vllm/vllm-openai:custom | gzip -9 -c >"$OUT/vllm-server.tar.gz"

# alpine: image tiện ích dùng bởi backup-minio-volume.sh / restore-minio-volume.sh
docker pull alpine:latest >/dev/null
docker save alpine:latest | gzip -9 -c >"$OUT/alpine.tar.gz"

echo "Xong → $OUT" >&2
ls -lh "$OUT" >&2
