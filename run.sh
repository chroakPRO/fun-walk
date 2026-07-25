#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

mode="${1:-}"
if [[ -z "$mode" ]]; then
  echo "You need to select a Docker mode: dev or prod." >&2
  echo "Usage: ./run.sh [dev|prod] [docker compose up options]" >&2
  exit 1
fi

shift

case "$mode" in
  dev|development)
    profile="dev"
    ;;
  prod|production)
    profile="prod"
    ;;
  -h|--help|help)
    echo "Usage: ./run.sh [dev|prod] [docker compose up options]"
    echo
    echo "  dev   Hot-reload backend and frontend with source mounts."
    echo "  prod  Build and run production containers without source mounts."
    exit 0
    ;;
  *)
    echo "Unknown mode: $mode" >&2
    echo "Usage: ./run.sh [dev|prod] [docker compose up options]" >&2
    exit 1
    ;;
esac

if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose=(docker-compose)
else
  echo "Docker Compose is required. Install Docker Desktop or docker-compose." >&2
  exit 1
fi

exec "${compose[@]}" --profile "$profile" up --build "$@"
