#!/usr/bin/env bash
# Load lại các .tar.gz do save.sh ghi vào offline/.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/offline"

gunzip -c "$DIR/alb.tar.gz" | docker load

gunzip -c "$DIR/general-chatbot-web.tar.gz" | docker load

gunzip -c "$DIR/chatbot-api.tar.gz" | docker load

gunzip -c "$DIR/chat-server.tar.gz" | docker load

gunzip -c "$DIR/db.tar.gz" | docker load

# minio.tar.gz chứa image đã commit từ container (config chỉnh tay), load về
# vẫn ra tag minio/minio:latest nên docker-compose.yaml không cần đổi gì.
# Nhớ chạy restore-minio-volume.sh (nếu có backup) TRƯỚC khi `docker compose up minio`
# để khôi phục bucket/user/policy trong volume minio_data.
gunzip -c "$DIR/minio.tar.gz" | docker load

gunzip -c "$DIR/media-service.tar.gz" | docker load

gunzip -c "$DIR/graph-extraction-job.tar.gz" | docker load

gunzip -c "$DIR/topic-classification-job.tar.gz" | docker load

gunzip -c "$DIR/file-processing-job.tar.gz" | docker load

gunzip -c "$DIR/omnivoice-tts.tar.gz" | docker load

gunzip -c "$DIR/vector-db-realtime-ingest.tar.gz" | docker load

gunzip -c "$DIR/vllm-server.tar.gz" | docker load

gunzip -c "$DIR/alpine.tar.gz" | docker load

echo "Đã load xong mọi image từ $DIR" >&2
