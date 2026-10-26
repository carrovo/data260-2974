#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h:h:h}"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
  print "Usage: reports/hw07/part4_agent_mac.zsh preflight|membership_wins|pay_per_use_wins|all"
  exit 2
fi

case "$1" in
  preflight)
    .venv/bin/python code/hw7_part4_runner.py preflight
    ;;
  membership_wins|pay_per_use_wins|all)
    .venv/bin/python code/hw7_part4_runner.py acceptance --scenario "$1"
    ;;
  *)
    print "Unknown mode: $1"
    exit 2
    ;;
esac
