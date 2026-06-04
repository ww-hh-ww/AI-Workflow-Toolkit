#!/usr/bin/env bash
set -eo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "$ROOT/tests/run-embedded-self-test.sh"
