#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HARNESS=""
REMAINING=()
EXPECT_HARNESS=false

for arg in "$@"; do
  if [[ "$EXPECT_HARNESS" == true ]]; then
    HARNESS="$arg"
    EXPECT_HARNESS=false
    continue
  fi
  if [[ "$arg" == "--harness" ]]; then
    EXPECT_HARNESS=true
    continue
  fi
  REMAINING+=("$arg")
done

if [[ -z "$HARNESS" ]]; then
  echo "Usage: $0 --harness <opencode|pi> [options...]" >&2
  echo "" >&2
  echo "Harnesses:" >&2
  echo "  opencode  Evaluate using OpenCode (evaluate-opencode.py)" >&2
  echo "  pi        Evaluate using pi (evaluate-pi.py)" >&2
  exit 1
fi

case "$HARNESS" in
  opencode)
    exec python3 "$SCRIPT_DIR/evaluate-opencode.py" "${REMAINING[@]+"${REMAINING[@]}"}"
    ;;
  pi)
    exec python3 "$SCRIPT_DIR/evaluate-pi.py" "${REMAINING[@]+"${REMAINING[@]}"}"
    ;;
  *)
    echo "Error: unknown harness '$HARNESS'. Use 'opencode' or 'pi'." >&2
    exit 1
    ;;
esac
