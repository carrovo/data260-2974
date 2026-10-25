#!/usr/bin/env bash

# Source this file so the six screenshot-group functions share runtime-only
# credentials. It supports Bash and macOS's default zsh. Do not enable shell
# xtrace because it would print secrets.
if [[ -n "${BASH_VERSION:-}" ]]; then
  HW7_DEMO_SCRIPT_SOURCE="${BASH_SOURCE[0]}"
  if [[ "${HW7_DEMO_SCRIPT_SOURCE}" == "$0" ]]; then
    echo "Source this file instead: source reports/hw07/demo_part1.sh" >&2
    exit 2
  fi
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  HW7_DEMO_SCRIPT_SOURCE="${(%):-%N}"
  if [[ "${ZSH_EVAL_CONTEXT:-}" != *:file* ]]; then
    echo "Source this file instead: source reports/hw07/demo_part1.sh" >&2
    exit 2
  fi
else
  echo "Use Bash or zsh to source this file." >&2
  return 2 2>/dev/null || exit 2
fi

HW7_DEMO_ROOT="$(
  cd "$(dirname "${HW7_DEMO_SCRIPT_SOURCE}")/../.." && pwd
)"
HW7_DEMO_CONTAINER="hw7-part1-demo-2974"
HW7_DEMO_DATABASE="hw7_part1_demo_2974"
HW7_DEMO_MYSQL_PORT="33374"
HW7_DEMO_API_PORT="38274"
HW7_DEMO_API_BASE="http://127.0.0.1:${HW7_DEMO_API_PORT}"
HW7_DEMO_APP_LOG="/tmp/hw7-part1-demo-api.log"


_hw7_demo_heading() {
  printf '\nStudent: Xuanhua Li\n'
  printf '===== %s =====\n' "$1"
}


_hw7_demo_preflight() {
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

  if [[ ! -x "${HW7_DEMO_ROOT}/.venv/bin/python" ]]; then
    echo "Missing project virtual environment: .venv/bin/python" >&2
    return 1
  fi

  if docker ps -a \
    --filter "name=^/${HW7_DEMO_CONTAINER}$" \
    --format '{{.ID}}' | grep -q .; then
    echo "Refusing to reuse container ${HW7_DEMO_CONTAINER}." >&2
    return 1
  fi

  if command -v ss >/dev/null 2>&1; then
    if ss -ltn | grep -Eq ":(${HW7_DEMO_MYSQL_PORT}|${HW7_DEMO_API_PORT})\\b"; then
      echo "A required demo port is already in use." >&2
      return 1
    fi
  fi
}


_hw7_demo_require_services() {
  if ! docker ps \
    --filter "name=^/${HW7_DEMO_CONTAINER}$" \
    --format '{{.ID}}' | grep -q .; then
    echo "Run hw7_demo_start first and keep that terminal open." >&2
    return 1
  fi

  if ! curl --fail --silent \
    "${HW7_DEMO_API_BASE}/health" >/dev/null; then
    echo "The temporary FastAPI service is not ready." >&2
    return 1
  fi
}


_hw7_demo_pretty_response() {
  local response_file="$1"

  if [[ ! -s "${response_file}" ]]; then
    echo "(empty response body)"
    return
  fi

  if ! "${HW7_DEMO_ROOT}/.venv/bin/python" \
    -m json.tool "${response_file}" 2>/dev/null; then
    sed -n '1,80p' "${response_file}"
  fi
}


_hw7_demo_request_to_file() {
  local role="$1"
  local method="$2"
  # `path` is a special parameter tied to PATH in zsh, so do not shadow it.
  local request_path="$3"
  local token="$4"
  local body="$5"
  local response_file="$6"
  local status_code
  local -a curl_args=(
    --silent
    --show-error
    --output "${response_file}"
    --write-out '%{http_code}'
    --request "${method}"
  )

  if [[ -n "${token}" ]]; then
    curl_args+=(
      --header "Authorization: Bearer ${token}"
    )
  fi

  if [[ -n "${body}" ]]; then
    curl_args+=(
      --header "Content-Type: application/json"
      --data "${body}"
    )
  fi

  printf 'REQUEST: %s %s\n' "${method}" "${request_path}"
  printf 'ROLE: %s\n' "${role}"
  status_code="$(
    curl "${curl_args[@]}" "${HW7_DEMO_API_BASE}${request_path}"
  )"
  printf 'HTTP_STATUS: %s\n' "${status_code}"
  echo "RESPONSE:"
  _hw7_demo_pretty_response "${response_file}"
  echo

  HW7_DEMO_LAST_STATUS="${status_code}"
}


_hw7_demo_request() {
  local response_file

  response_file="$(mktemp /tmp/hw7-demo-response.XXXXXX)"
  _hw7_demo_request_to_file "$@" "${response_file}"
  rm -f "${response_file}"
}


_hw7_demo_token() {
  local role="$1"
  local response

  response="$(
    curl --fail --silent --show-error \
      --header "Content-Type: application/json" \
      --data "{\"username\":\"demo-${role}\",\"password\":\"${HW7_DEMO_USER_PASSWORD}\"}" \
      "${HW7_DEMO_API_BASE}/auth/login"
  )" || return 1

  printf '%s' "${response}" | "${HW7_DEMO_ROOT}/.venv/bin/python" \
    -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}


_hw7_demo_listing_body() {
  local listing_code="$1"

  printf '%s' \
    "{\"listingTitle\":\"HW7 Demo Apartment\"," \
    "\"listingCode\":\"${listing_code}\"," \
    "\"address\":\"2974 Demo Avenue\"," \
    "\"submitterEmail\":\"demo@example.com\"," \
    "\"description\":\"Temporary listing for the HW7 Part 1 HTTP demo.\"," \
    "\"propertyType\":\"Apartment\"," \
    "\"monthlyRent\":\"2100.00\"," \
    "\"availableUnits\":1," \
    "\"termsAccepted\":true," \
    "\"propertyManagerId\":1}"
}


hw7_demo_start() {
  local attempt mysql_ready seed_status

  _hw7_demo_preflight || return 1

  export HW7_DEMO_DB_PASSWORD
  export HW7_DEMO_JWT_SECRET
  export HW7_DEMO_USER_PASSWORD
  export HW7_DEMO_BAD_PASSWORD
  export HW7_DEMO_DATABASE_URL

  HW7_DEMO_DB_PASSWORD="$(openssl rand -hex 24)"
  HW7_DEMO_JWT_SECRET="$(openssl rand -hex 48)"
  HW7_DEMO_USER_PASSWORD="$(openssl rand -hex 18)"
  HW7_DEMO_BAD_PASSWORD="$(openssl rand -hex 18)"
  HW7_DEMO_DATABASE_URL="mysql+pymysql://root:${HW7_DEMO_DB_PASSWORD}@127.0.0.1:${HW7_DEMO_MYSQL_PORT}/${HW7_DEMO_DATABASE}"

  docker run --rm --detach \
    --name "${HW7_DEMO_CONTAINER}" \
    --publish "127.0.0.1:${HW7_DEMO_MYSQL_PORT}:3306" \
    --env "MYSQL_ROOT_PASSWORD=${HW7_DEMO_DB_PASSWORD}" \
    --env "MYSQL_ROOT_HOST=%" \
    --env "MYSQL_DATABASE=${HW7_DEMO_DATABASE}" \
    mysql:8.4 --skip-log-bin >/dev/null || {
      hw7_demo_stop
      return 1
    }

  # The official entrypoint briefly starts an initialization server before
  # the final TCP listener. Require the same host-side driver connection that
  # the application will use instead of relying on an early mysqladmin ping.
  mysql_ready="false"
  for ((attempt = 1; attempt <= 90; attempt++)); do
    if DATABASE_URL="${HW7_DEMO_DATABASE_URL}" \
      "${HW7_DEMO_ROOT}/.venv/bin/python" -c \
      'from sqlalchemy import create_engine, text; import os; engine = create_engine(os.environ["DATABASE_URL"]); connection = engine.connect(); connection.execute(text("SELECT 1")); connection.close(); engine.dispose()' \
      >/dev/null 2>&1; then
      mysql_ready="true"
      break
    fi
    sleep 1
  done

  if [[ "${mysql_ready}" != "true" ]]; then
    echo "Temporary MySQL did not accept the application connection." >&2
    hw7_demo_stop
    return 1
  fi

  DATABASE_URL="${HW7_DEMO_DATABASE_URL}" \
  HW7_DEMO_USER_PASSWORD="${HW7_DEMO_USER_PASSWORD}" \
  PYTHONPATH="${HW7_DEMO_ROOT}:${HW7_DEMO_ROOT}/code" \
    "${HW7_DEMO_ROOT}/.venv/bin/python" - <<'PY'
import os

from sqlalchemy.orm import Session

from auth_service import hash_password
from database import Base, db_session_basede26
from migrate_hw7_users import migrate_user_schema
from models import PropertyManager, User, UserRole


Base.metadata.create_all(bind=db_session_basede26)
migrate_user_schema(db_session_basede26)

password_hash = hash_password(os.environ["HW7_DEMO_USER_PASSWORD"])

with Session(db_session_basede26) as session:
    session.add_all(
        [
            User(
                name=f"Demo {role.value.title()}",
                email=f"demo-{role.value}@example.com",
                username=f"demo-{role.value}",
                password_hash=password_hash,
                role=role,
            )
            for role in UserRole
        ]
        + [
            PropertyManager(
                firstName="Demo",
                lastName="Manager",
                email="demo-manager@example.com",
            )
        ]
    )
    session.commit()
PY

  seed_status=$?
  if [[ "${seed_status}" != "0" ]]; then
    echo "Unable to initialize the isolated demo database." >&2
    hw7_demo_stop
    return 1
  fi

  (
    cd "${HW7_DEMO_ROOT}/code" || exit 1
    exec env \
      DATABASE_URL="${HW7_DEMO_DATABASE_URL}" \
      JWT_SECRET_KEY="${HW7_DEMO_JWT_SECRET}" \
      JWT_ACCESS_TOKEN_MINUTES="30" \
      MONGODB_URI="mongodb://127.0.0.1:1" \
      PYTHONPATH="${HW7_DEMO_ROOT}:${HW7_DEMO_ROOT}/code" \
      "${HW7_DEMO_ROOT}/.venv/bin/python" -m uvicorn \
      main:app --host 127.0.0.1 --port "${HW7_DEMO_API_PORT}"
  ) >"${HW7_DEMO_APP_LOG}" 2>&1 &
  export HW7_DEMO_APP_PID=$!

  for ((attempt = 1; attempt <= 60; attempt++)); do
    if curl --fail --silent \
      "${HW7_DEMO_API_BASE}/health" >/dev/null 2>&1; then
      echo "HW7 demo services are ready."
      echo "Keep this terminal open; then run groups 1 through 6."
      return 0
    fi

    if ! kill -0 "${HW7_DEMO_APP_PID}" 2>/dev/null; then
      echo "FastAPI exited before readiness." >&2
      sed -n '1,120p' "${HW7_DEMO_APP_LOG}" >&2
      hw7_demo_stop
      return 1
    fi
    sleep 1
  done

  echo "FastAPI did not become ready." >&2
  hw7_demo_stop
  return 1
}


hw7_demo_group_1() {
  local success_body failure_body

  _hw7_demo_require_services || return 1
  _hw7_demo_heading "1. Successful and failed login"

  success_body="{\"username\":\"demo-reader\",\"password\":\"${HW7_DEMO_USER_PASSWORD}\"}"
  failure_body="{\"username\":\"demo-reader\",\"password\":\"${HW7_DEMO_BAD_PASSWORD}\"}"

  _hw7_demo_request \
    "reader (valid credentials)" \
    "POST" "/auth/login" "" "${success_body}"
  _hw7_demo_request \
    "reader (invalid credentials)" \
    "POST" "/auth/login" "" "${failure_body}"
}


hw7_demo_group_2() {
  _hw7_demo_require_services || return 1
  _hw7_demo_heading "2. /auth/me without a token"

  _hw7_demo_request \
    "anonymous (no token)" \
    "GET" "/auth/me" "" ""
}


hw7_demo_group_3() {
  _hw7_demo_require_services || return 1
  _hw7_demo_heading "3. /auth/me with an invalid token"

  _hw7_demo_request \
    "anonymous (invalid temporary token)" \
    "GET" "/auth/me" "not-a-valid-jwt" ""
}


hw7_demo_group_4() {
  local reader_token writer_token listing_code listing_body response_file

  _hw7_demo_require_services || return 1
  _hw7_demo_heading "4. Reader create 403 and writer create 201"

  reader_token="$(_hw7_demo_token reader)" || return 1
  writer_token="$(_hw7_demo_token writer)" || return 1
  listing_code="DEMO4-${RANDOM}-$(date +%s)"
  listing_body="$(_hw7_demo_listing_body "${listing_code}")"

  _hw7_demo_request \
    "reader" "POST" "/api/listings" \
    "${reader_token}" "${listing_body}"

  response_file="$(mktemp /tmp/hw7-demo-writer-create.XXXXXX)"
  _hw7_demo_request_to_file \
    "writer" "POST" "/api/listings" \
    "${writer_token}" "${listing_body}" "${response_file}"

  if [[ "${HW7_DEMO_LAST_STATUS}" != "201" ]]; then
    rm -f "${response_file}"
    return 1
  fi

  export HW7_DEMO_LAST_LISTING_ID
  HW7_DEMO_LAST_LISTING_ID="$(
    "${HW7_DEMO_ROOT}/.venv/bin/python" -c \
      'import json, sys; print(json.load(open(sys.argv[1]))["id"])' \
      "${response_file}"
  )"
  rm -f "${response_file}"
}


hw7_demo_group_5() {
  local writer_token moderator_token listing_code listing_body
  local create_file create_status listing_id

  _hw7_demo_require_services || return 1
  _hw7_demo_heading "5. Writer delete 403 and moderator delete success"

  writer_token="$(_hw7_demo_token writer)" || return 1
  moderator_token="$(_hw7_demo_token moderator)" || return 1
  listing_code="DEMO5-${RANDOM}-$(date +%s)"
  listing_body="$(_hw7_demo_listing_body "${listing_code}")"
  create_file="$(mktemp /tmp/hw7-demo-delete-target.XXXXXX)"

  create_status="$(
    curl --silent --show-error \
      --output "${create_file}" \
      --write-out '%{http_code}' \
      --header "Authorization: Bearer ${writer_token}" \
      --header "Content-Type: application/json" \
      --data "${listing_body}" \
      "${HW7_DEMO_API_BASE}/api/listings"
  )"

  if [[ "${create_status}" != "201" ]]; then
    echo "Unable to prepare the temporary delete target." >&2
    _hw7_demo_pretty_response "${create_file}" >&2
    rm -f "${create_file}"
    return 1
  fi

  listing_id="$(
    "${HW7_DEMO_ROOT}/.venv/bin/python" -c \
      'import json, sys; print(json.load(open(sys.argv[1]))["id"])' \
      "${create_file}"
  )"
  rm -f "${create_file}"

  _hw7_demo_request \
    "writer" "DELETE" "/api/listings/${listing_id}" \
    "${writer_token}" ""
  _hw7_demo_request \
    "moderator" "DELETE" "/api/listings/${listing_id}" \
    "${moderator_token}" ""
}


hw7_demo_group_6() {
  local reader_token

  _hw7_demo_require_services || return 1
  _hw7_demo_heading "6. Authenticated reader list request"

  reader_token="$(_hw7_demo_token reader)" || return 1
  _hw7_demo_request \
    "reader" "GET" "/api/listings?page_size=50" \
    "${reader_token}" ""
}


hw7_demo_stop() {
  if [[ -n "${HW7_DEMO_APP_PID:-}" ]] && \
    kill -0 "${HW7_DEMO_APP_PID}" 2>/dev/null; then
    kill "${HW7_DEMO_APP_PID}" 2>/dev/null || true
    wait "${HW7_DEMO_APP_PID}" 2>/dev/null || true
  fi

  if docker ps -a \
    --filter "name=^/${HW7_DEMO_CONTAINER}$" \
    --format '{{.ID}}' | grep -q .; then
    docker stop "${HW7_DEMO_CONTAINER}" >/dev/null
  fi

  unset HW7_DEMO_APP_PID
  unset HW7_DEMO_DB_PASSWORD
  unset HW7_DEMO_JWT_SECRET
  unset HW7_DEMO_USER_PASSWORD
  unset HW7_DEMO_BAD_PASSWORD
  unset HW7_DEMO_DATABASE_URL
  unset HW7_DEMO_LAST_LISTING_ID
  unset HW7_DEMO_LAST_STATUS
  unset HW7_DEMO_SCRIPT_SOURCE

  echo "HW7 demo services stopped; the temporary database was removed."
}
