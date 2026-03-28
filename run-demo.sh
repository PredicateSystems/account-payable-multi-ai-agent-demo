#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

MODE="${RUN_MODE:-docker}"
LLM_MODE="${LLM_MODE:-cloud}"
ACTION="run"
DRY_RUN="false"
SKIP_SIDECAR="false"
NO_DOWNLOAD_SIDECAR="false"
STARTED_SIDECAR="false"

BIN_DIR="$SCRIPT_DIR/.bin"
TMP_DIR="$SCRIPT_DIR/.tmp"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$TMP_DIR/sidecar.pid"
SIDECAR_BIN="$BIN_DIR/predicate-authorityd"

mkdir -p "$BIN_DIR" "$TMP_DIR" "$LOG_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

print_help() {
  cat <<EOF
Usage: ./run-demo.sh [--docker|--local] [--llm cloud|local] [options]

Modes:
  --docker              Run demo runner in Docker (default)
  --local               Run demo runner on host machine
  --llm cloud           Use hosted model providers
  --llm local           Use host-machine Ollama

Options:
  --down                Stop locally started sidecar and docker services
  --dry-run             Print actions without executing them
  --skip-sidecar        Do not auto-start a local sidecar
  --no-download-sidecar Disable automatic sidecar binary download
  -h, --help            Show this help

Expected setup matrix:
  1. Docker + cloud      -> easiest first-run path
  2. Docker + host Ollama -> local-model story with containerized demo runner
  3. Local + cloud       -> developer iteration
  4. Local + host Ollama -> fully local development
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --docker)
      MODE="docker"
      shift
      ;;
    --local)
      MODE="local"
      shift
      ;;
    --llm)
      LLM_MODE="${2:-}"
      if [[ "$LLM_MODE" != "cloud" && "$LLM_MODE" != "local" ]]; then
        echo -e "${RED}Invalid --llm value: ${LLM_MODE}${NC}"
        exit 1
      fi
      shift 2
      ;;
    --down)
      ACTION="down"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --skip-sidecar)
      SKIP_SIDECAR="true"
      shift
      ;;
    --no-download-sidecar)
      NO_DOWNLOAD_SIDECAR="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      print_help
      exit 1
      ;;
  esac
done

say() {
  printf "%b\n" "$1"
}

run_cmd() {
  if [ "$DRY_RUN" = "true" ]; then
    say "${YELLOW}[dry-run] $*${NC}"
    return 0
  fi
  "$@"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    say "${RED}Missing required command: $1${NC}"
    exit 1
  fi
}

health_check() {
  local url="$1"
  curl -sf "${url}/health" >/dev/null 2>&1
}

detect_os() {
  case "$(uname -s)" in
    Darwin) echo "darwin" ;;
    Linux) echo "linux" ;;
    *) echo "unsupported" ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    arm64|aarch64) echo "arm64" ;;
    x86_64|amd64) echo "x86_64" ;;
    *) echo "unsupported" ;;
  esac
}

resolve_sidecar_download_url() {
  local repo="${SIDECAR_RELEASE_REPO:-PredicateSystems/predicate-authority-sidecar}"
  local version="${SIDECAR_VERSION:-latest}"
  local os arch api_url
  os="$(detect_os)"
  arch="$(detect_arch)"

  if [[ "$os" = "unsupported" || "$arch" = "unsupported" ]]; then
    return 1
  fi

  if [[ "$version" = "latest" ]]; then
    api_url="https://api.github.com/repos/${repo}/releases/latest"
  else
    api_url="https://api.github.com/repos/${repo}/releases/tags/${version}"
  fi

  curl -fsSL "$api_url" | python3 - "$os" "$arch" <<'PY'
import json
import sys

os_name = sys.argv[1]
arch = sys.argv[2]
data = json.load(sys.stdin)

assets = data.get("assets", [])
needles = [
    "predicate",
    "authority",
    os_name,
    arch,
]

def score(name: str) -> int:
    lower = name.lower()
    return sum(1 for n in needles if n in lower)

best = None
best_score = -1
for asset in assets:
    name = asset.get("name", "")
    s = score(name)
    if s > best_score:
        best = asset.get("browser_download_url")
        best_score = s

if not best:
    sys.exit(1)

print(best)
PY
}

download_sidecar() {
  if [ -x "$SIDECAR_BIN" ]; then
    return 0
  fi

  if [ "$NO_DOWNLOAD_SIDECAR" = "true" ]; then
    say "${YELLOW}Sidecar binary not found and auto-download disabled.${NC}"
    return 1
  fi

  require_cmd curl
  require_cmd python3

  say "${CYAN}Resolving sidecar release asset...${NC}"
  local url
  if ! url="$(resolve_sidecar_download_url)"; then
    say "${YELLOW}Could not resolve a matching sidecar release asset automatically.${NC}"
    return 1
  fi

  local archive="$TMP_DIR/sidecar-download"
  say "${CYAN}Downloading sidecar from:${NC} ${url}"
  run_cmd curl -fsSL "$url" -o "$archive"

  case "$url" in
    *.tar.gz|*.tgz)
      run_cmd tar -xzf "$archive" -C "$TMP_DIR"
      ;;
    *.zip)
      run_cmd python3 - "$archive" "$TMP_DIR" <<'PY'
import sys
import zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY
      ;;
    *)
      run_cmd mv "$archive" "$SIDECAR_BIN"
      run_cmd chmod +x "$SIDECAR_BIN"
      return 0
      ;;
  esac

  local found
  found="$(python3 - "$TMP_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
for path in root.rglob("*"):
    if path.is_file() and "predicate-authorityd" in path.name:
        print(path)
        break
PY
)"
  if [ -z "$found" ] || [ ! -f "$found" ]; then
    say "${YELLOW}Downloaded release asset did not contain a detectable sidecar binary.${NC}"
    return 1
  fi

  run_cmd cp "$found" "$SIDECAR_BIN"
  run_cmd chmod +x "$SIDECAR_BIN"
}

cleanup_sidecar() {
  if [ "$STARTED_SIDECAR" = "true" ] && [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$PID_FILE"
  fi
}

trap cleanup_sidecar EXIT

start_sidecar_if_needed() {
  if [ "$SKIP_SIDECAR" = "true" ]; then
    say "${YELLOW}Skipping local sidecar startup by request.${NC}"
    return 0
  fi

  local sidecar_url="${PREDICATE_SIDECAR_URL:-http://localhost:8787}"
  local policy_path="${SIDECAR_POLICY_PATH:-./policy.yaml}"

  if health_check "$sidecar_url"; then
    say "${GREEN}Using existing sidecar at ${sidecar_url}${NC}"
    return 0
  fi

  if ! download_sidecar; then
    say "${YELLOW}Automatic sidecar bootstrap failed.${NC}"
    say "${YELLOW}Manual fallback:${NC}"
    say "  1. Download the correct predicate-authorityd release for your OS"
    say "  2. Run it with: predicate-authorityd --policy-file ${policy_path}"
    return 1
  fi

  say "${CYAN}Starting local sidecar with policy ${policy_path}${NC}"
  if [ "$DRY_RUN" = "true" ]; then
    say "${YELLOW}[dry-run] ${SIDECAR_BIN} --policy-file ${policy_path}${NC}"
    return 0
  fi

  "$SIDECAR_BIN" --policy-file "$policy_path" >"$LOG_DIR/sidecar.log" 2>&1 &
  echo $! > "$PID_FILE"
  STARTED_SIDECAR="true"

  for _ in $(seq 1 30); do
    if health_check "$sidecar_url"; then
      say "${GREEN}Sidecar is healthy at ${sidecar_url}${NC}"
      return 0
    fi
    sleep 1
  done

  say "${RED}Sidecar failed to become healthy. Check logs/sidecar.log${NC}"
  return 1
}

ensure_ollama_if_needed() {
  if [ "$LLM_MODE" != "local" ]; then
    return 0
  fi

  local raw_url="${OLLAMA_BASE_URL:-http://localhost:11434}"
  local host_check_url="${OLLAMA_HOST_CHECK_URL:-$raw_url}"
  host_check_url="${host_check_url/host.docker.internal/localhost}"

  say "${CYAN}Checking Ollama at ${host_check_url}${NC}"
  if ! curl -sf "${host_check_url}/api/tags" >/dev/null 2>&1; then
    say "${RED}Ollama is not reachable at ${host_check_url}${NC}"
    say "Start it with: ollama serve"
    exit 1
  fi
  say "${GREEN}Ollama is reachable${NC}"
}

docker_compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

run_local() {
  require_cmd python3
  start_sidecar_if_needed || true
  ensure_ollama_if_needed

  say "${CYAN}Running demo locally${NC}"
  run_cmd python3 main.py --mode local --llm "$LLM_MODE"
}

run_docker() {
  require_cmd docker
  local compose_cmd
  if ! compose_cmd="$(docker_compose_cmd)"; then
    say "${RED}Docker Compose is required for docker mode.${NC}"
    exit 1
  fi

  start_sidecar_if_needed || true
  ensure_ollama_if_needed

  local container_sidecar_url="${CONTAINER_SIDECAR_URL:-http://host.docker.internal:8787}"
  local container_ollama_url="${CONTAINER_OLLAMA_URL:-http://host.docker.internal:11434}"

  say "${CYAN}Running demo in Docker${NC}"
  if [ "$DRY_RUN" = "true" ]; then
    say "${YELLOW}[dry-run] PREDICATE_SIDECAR_URL=${container_sidecar_url} OLLAMA_BASE_URL=${container_ollama_url} ${compose_cmd} run --rm demo-runner${NC}"
    return 0
  fi

  PREDICATE_SIDECAR_URL="$container_sidecar_url" \
  OLLAMA_BASE_URL="$container_ollama_url" \
  LLM_MODE="$LLM_MODE" \
  $compose_cmd run --rm demo-runner
}

down_mode() {
  say "${CYAN}Stopping demo resources${NC}"

  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      run_cmd kill "$pid"
      say "${GREEN}Stopped local sidecar (pid ${pid})${NC}"
    fi
    rm -f "$PID_FILE"
  fi

  if compose_cmd="$(docker_compose_cmd 2>/dev/null)"; then
    run_cmd $compose_cmd down >/dev/null 2>&1 || true
  fi
}

say "${CYAN}${BOLD}====================================================================${NC}"
say "${CYAN}${BOLD} Account Payable Demo Launcher${NC}"
say "${CYAN}${BOLD}====================================================================${NC}"
say "Mode:      ${MODE}"
say "LLM mode:  ${LLM_MODE}"
say "Action:    ${ACTION}"
say ""

if [ "$ACTION" = "down" ]; then
  down_mode
  exit 0
fi

case "$MODE" in
  local) run_local ;;
  docker) run_docker ;;
  *)
    say "${RED}Unsupported mode: ${MODE}${NC}"
    exit 1
    ;;
esac
