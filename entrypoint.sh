#!/bin/sh
# Entrypoint delegates process orchestration to run.py.
# Usage: docker run ... [api|worker|flower|both|all]

set -e

exec python run.py "${1:-all}"
