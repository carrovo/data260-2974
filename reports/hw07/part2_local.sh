#!/usr/bin/env bash

# Source this helper from Bash or macOS zsh so its runtime-only database
# credentials remain available to the Part 2 runner. Never enable xtrace.
if [[ -n "${BASH_VERSION:-}" ]]; then
  HW7_PART2_SCRIPT_SOURCE="${BASH_SOURCE[0]}"
  if [[ "${HW7_PART2_SCRIPT_SOURCE}" == "$0" ]]; then
    echo "Source this file: source reports/hw07/part2_local.sh" >&2
    exit 2
  fi
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  HW7_PART2_SCRIPT_SOURCE="${(%):-%N}"
  if [[ "${ZSH_EVAL_CONTEXT:-}" != *:file* ]]; then
    echo "Source this file: source reports/hw07/part2_local.sh" >&2
    exit 2
  fi
else
  echo "Use Bash or zsh to source this file." >&2
  return 2 2>/dev/null || exit 2
fi

HW7_PART2_ROOT="$(
  cd "$(dirname "${HW7_PART2_SCRIPT_SOURCE}")/../.." && pwd
)"
HW7_PART2_CONTAINER="hw7-part2-mysql-2974"
HW7_PART2_DATABASE="hw7_part2_fixture_2974"
HW7_PART2_MYSQL_PORT="33375"


_hw7_part2_preflight() {
  local command_name

  if [[ "$-" == *x* ]]; then
    echo "Disable shell xtrace with: set +x" >&2
    return 1
  fi

  for command_name in docker curl openssl; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
      echo "Required command is unavailable: ${command_name}" >&2
      return 1
    fi
  done

  if [[ ! -x "${HW7_PART2_ROOT}/.venv/bin/python" ]]; then
    echo "Missing project virtual environment: .venv/bin/python" >&2
    return 1
  fi

  if docker ps -a \
    --filter "name=^/${HW7_PART2_CONTAINER}$" \
    --format '{{.ID}}' | grep -q .; then
    echo "Refusing to reuse container ${HW7_PART2_CONTAINER}." >&2
    return 1
  fi
}


hw7_part2_start() {
  local attempt mysql_ready

  _hw7_part2_preflight || return 1

  export HW7_PART2_DB_PASSWORD
  export HW7_PART2_ISOLATED="1"
  export DATABASE_URL
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

  HW7_PART2_DB_PASSWORD="$(openssl rand -hex 24)"
  DATABASE_URL="mysql+pymysql://root:${HW7_PART2_DB_PASSWORD}@127.0.0.1:${HW7_PART2_MYSQL_PORT}/${HW7_PART2_DATABASE}"

  docker run --rm --detach \
    --name "${HW7_PART2_CONTAINER}" \
    --publish "127.0.0.1:${HW7_PART2_MYSQL_PORT}:3306" \
    --env "MYSQL_ROOT_PASSWORD=${HW7_PART2_DB_PASSWORD}" \
    --env "MYSQL_ROOT_HOST=%" \
    --env "MYSQL_DATABASE=${HW7_PART2_DATABASE}" \
    mysql:8.4 --skip-log-bin >/dev/null || {
      hw7_part2_stop
      return 1
    }

  mysql_ready="false"
  for ((attempt = 1; attempt <= 90; attempt++)); do
    if "${HW7_PART2_ROOT}/.venv/bin/python" -c \
      'from sqlalchemy import create_engine, text; import os; engine = create_engine(os.environ["DATABASE_URL"]); connection = engine.connect(); connection.execute(text("SELECT 1")); connection.close(); engine.dispose()' \
      >/dev/null 2>&1; then
      mysql_ready="true"
      break
    fi
    sleep 1
  done

  if [[ "${mysql_ready}" != "true" ]]; then
    echo "Temporary MySQL did not accept the fixture connection." >&2
    hw7_part2_stop
    return 1
  fi

  (
    cd "${HW7_PART2_ROOT}" || exit 1
    "${HW7_PART2_ROOT}/.venv/bin/python" \
      code/hw7_part2_runner.py preflight --reset-fixture
  ) || {
    echo "Part 2 preflight failed; the temporary database will be removed." >&2
    hw7_part2_stop
    return 1
  }

  echo "HW7 Part 2 fixture is ready."
  echo "Keep this terminal and Ollama running while executing the runner."
}


hw7_part2_stop() {
  local attempt

  if docker ps -a \
    --filter "name=^/${HW7_PART2_CONTAINER}$" \
    --format '{{.ID}}' | grep -q .; then
    docker stop "${HW7_PART2_CONTAINER}" >/dev/null
  fi

  # Docker's --rm removal can finish just after `docker stop` returns.
  for ((attempt = 1; attempt <= 20; attempt++)); do
    if ! docker ps -a \
      --filter "name=^/${HW7_PART2_CONTAINER}$" \
      --format '{{.ID}}' | grep -q .; then
      break
    fi
    sleep 0.2
  done

  unset HW7_PART2_DB_PASSWORD
  unset HW7_PART2_ISOLATED
  unset DATABASE_URL
  unset HW7_PART2_SCRIPT_SOURCE

  echo "HW7 Part 2 fixture stopped and its temporary database was removed."
}
