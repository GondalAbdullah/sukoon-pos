#!/usr/bin/env bash
# Local test runner. Mirrors "How the Agent Verifies a Phase Is Actually Done"
# (Development Specification, Section 11): a clean lint pass, then the full
# test suite with coverage. Exits non-zero if either fails.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> ruff (lint)"
ruff check .

echo "==> pytest (coverage)"
coverage run -m pytest
coverage report -m
