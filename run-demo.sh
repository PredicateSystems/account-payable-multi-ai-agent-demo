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

# Use Python module for health check
health_check() {
  local url="$1"
  python3 -c "
from account_payable_demo.sidecar import health_check
import sys
sys.exit(0 if health_check('$url') else 1)
" 2>/dev/null
}

# Use Python module for platform detection
detect_platform() {
  python3 -c "
from account_payable_demo.sidecar import detect_platform
plat = detect_platform()
if plat:
    print(f'{plat.os.value}-{plat.arch.value}')
else:
    print('unsupported')
" 2>/dev/null || echo "unsupported"
}

# Use Python module to resolve sidecar download URL
resolve_sidecar_download_url() {
  python3 -c "
from account_payable_demo.sidecar import resolve_download_url
import sys
url = resolve_download_url()
if url:
    print(url)
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null
}

# Use Python module for download with fallback to shell
download_sidecar() {
  if [ -x "$SIDECAR_BIN" ]; then
    return 0
  fi

  if [ "$DRY_RUN" = "true" ]; then
    say "${YELLOW}[dry-run] Would download sidecar binary to ${SIDECAR_BIN}${NC}"
    return 0
  fi

  if [ "$NO_DOWNLOAD_SIDECAR" = "true" ]; then
    say "${YELLOW}Sidecar binary not found and auto-download disabled.${NC}"
    return 1
  fi

  require_cmd python3

  say "${CYAN}Attempting sidecar download via Python module...${NC}"

  # Try Python-based download first
  local result
  result=$(python3 -c "
from account_payable_demo.sidecar import download_sidecar
from account_payable_demo.config import SidecarConfig
from pathlib import Path
import json

config = SidecarConfig()
bin_dir = Path('$BIN_DIR')
tmp_dir = Path('$TMP_DIR')

result = download_sidecar(config, bin_dir, tmp_dir)
print(json.dumps({
    'success': result.success,
    'binary_path': str(result.binary_path) if result.binary_path else None,
    'error': result.error
}))
" 2>/dev/null) || result='{"success": false, "error": "Python module failed"}'

  local success
  success=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success', False))")

  if [ "$success" = "True" ]; then
    say "${GREEN}Sidecar downloaded successfully${NC}"
    return 0
  fi

  local error
  error=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error', 'Unknown error'))")
  say "${YELLOW}Python download failed: ${error}${NC}"

  # Fallback to shell-based download
  say "${CYAN}Falling back to shell-based download...${NC}"
  require_cmd curl

  local url
  if ! url="$(resolve_sidecar_download_url)"; then
    say "${YELLOW}Could not resolve a matching sidecar release asset automatically.${NC}"
    print_manual_instructions
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
      run_cmd python3 -c "import zipfile; zipfile.ZipFile('$archive').extractall('$TMP_DIR')"
      ;;
    *)
      run_cmd mv "$archive" "$SIDECAR_BIN"
      run_cmd chmod +x "$SIDECAR_BIN"
      return 0
      ;;
  esac

  # Find binary in extracted archive
  local found
  found="$(python3 -c "
from account_payable_demo.sidecar import find_binary_in_dir
from pathlib import Path
result = find_binary_in_dir(Path('$TMP_DIR'))
if result:
    print(result)
" 2>/dev/null)"

  if [ -z "$found" ] || [ ! -f "$found" ]; then
    say "${YELLOW}Downloaded release asset did not contain a detectable sidecar binary.${NC}"
    return 1
  fi

  run_cmd cp "$found" "$SIDECAR_BIN"
  run_cmd chmod +x "$SIDECAR_BIN"
}

print_manual_instructions() {
  python3 -c "
from account_payable_demo.sidecar import get_manual_install_instructions
print(get_manual_install_instructions())
" 2>/dev/null || cat <<EOF
Manual fallback:
  1. Download the correct predicate-authorityd release for your OS
     from: https://github.com/PredicateSystems/predicate-authority-sidecar/releases/latest
  2. Extract and place 'predicate-authorityd' in .bin/ directory
  3. Run: predicate-authorityd --policy-file ./policy.yaml
EOF
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
    print_manual_instructions
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

  # Use Python for waiting with health checks
  say "${CYAN}Waiting for sidecar to become healthy...${NC}"
  if python3 -c "
from account_payable_demo.sidecar import wait_for_healthy
import sys
sys.exit(0 if wait_for_healthy('$sidecar_url', max_attempts=30) else 1)
" 2>/dev/null; then
    say "${GREEN}Sidecar is healthy at ${sidecar_url}${NC}"
    return 0
  fi

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

# Print detected platform info
print_platform_info() {
  local platform_info
  platform_info=$(detect_platform)
  if [ "$platform_info" != "unsupported" ]; then
    say "Platform:  ${platform_info}"
  else
    say "Platform:  ${YELLOW}unsupported (manual sidecar install required)${NC}"
  fi
}

say "${CYAN}${BOLD}====================================================================${NC}"
say "${CYAN}${BOLD} Account Payable Demo Launcher${NC}"
say "${CYAN}${BOLD}====================================================================${NC}"
say "Mode:      ${MODE}"
say "LLM mode:  ${LLM_MODE}"
print_platform_info
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
