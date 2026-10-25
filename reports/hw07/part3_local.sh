#!/usr/bin/env bash

# Source this file from Bash or macOS zsh. It reuses the guarded Part 2
# temporary MySQL fixture and never connects to a personal database.
if [[ -n "${BASH_VERSION:-}" ]]; then
  HW7_PART3_SCRIPT_SOURCE="${BASH_SOURCE[0]}"
  if [[ "${HW7_PART3_SCRIPT_SOURCE}" == "$0" ]]; then
    echo "Source this file: source reports/hw07/part3_local.sh" >&2
    exit 2
  fi
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  HW7_PART3_SCRIPT_SOURCE="${(%):-%N}"
  if [[ "${ZSH_EVAL_CONTEXT:-}" != *:file* ]]; then
    echo "Source this file: source reports/hw07/part3_local.sh" >&2
    exit 2
  fi
else
  echo "Use Bash or zsh to source this file." >&2
  return 2 2>/dev/null || exit 2
fi

HW7_PART3_ROOT="$(
  cd "$(dirname "${HW7_PART3_SCRIPT_SOURCE}")/../.." && pwd
)"

source "${HW7_PART3_ROOT}/reports/hw07/part2_local.sh"


hw7_part3_start() {
  hw7_part2_start || return 1
  echo "HW7 Part 3 reuses the ready isolated Part 2 fixture."
}


hw7_part3_stop() {
  hw7_part2_stop
  unset HW7_PART3_SCRIPT_SOURCE
}
