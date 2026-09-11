#!/usr/bin/env sh
# Compile the Tailwind stylesheet. The output (sukoon/static/css/tailwind.css) is
# committed — Development Spec §5.1: no Node runtime ships in the installer, only
# the static .css. Run this after editing a template or input.css.
set -e
cd "$(dirname "$0")/.."

if [ ! -x node_modules/.bin/tailwindcss ]; then
  echo "tailwindcss not installed — run: npm install" >&2
  exit 1
fi

node_modules/.bin/tailwindcss \
  -c tailwind.config.js \
  -i sukoon/static/css/input.css \
  -o sukoon/static/css/tailwind.css \
  --minify

echo "built sukoon/static/css/tailwind.css"
