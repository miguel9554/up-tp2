#!/usr/bin/env bash
# Run any command inside the LibreLane container.
#
# Usage: ./run.sh [command [args...]]
#   ./run.sh                          # interactive shell
#   ./run.sh openroad -version
#   ./run.sh librelane --help
#
# This directory is mounted at /work (the working directory), so use
# paths relative to it. If TP1_RUN is set, that directory (a TP1 run) is
# mounted read-only at /tp1_run. If DISPLAY is set, the X11 socket is shared
# so GUIs (OpenROAD, KLayout) open on the host's screen.
set -euo pipefail

LIBRELANE_TAG="${LIBRELANE_TAG:-3.0.14}"
PDK_ROOT_HOST="${PDK_ROOT_HOST:-$HOME/.ciel}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$PDK_ROOT_HOST"

# Only allocate a TTY when we actually have one (e.g. not in make/CI/pipes).
TTY_FLAGS=(-i)
[ -t 0 ] && [ -t 1 ] && TTY_FLAGS=(-it)

EXTRA=()
if [ -n "${TP1_RUN:-}" ]; then
  EXTRA+=(-v "$(cd "$TP1_RUN" && pwd):/tp1_run:ro")
fi
if [ -n "${DISPLAY:-}" ] && [ -d /tmp/.X11-unix ]; then
  # The container runs with the host uid, so `xhost +SI:localuser:$USER`
  # (done by `make gui`) is enough to authorize it on the X server.
  EXTRA+=(-e DISPLAY -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix:ro)
fi

[ "$#" -eq 0 ] && set -- bash

exec docker run --rm "${TTY_FLAGS[@]}" \
  -u "$(id -u):$(id -g)" \
  -v "$PROJECT_DIR:/work" \
  -v "$PDK_ROOT_HOST:/pdks" \
  -e PDK_ROOT=/pdks \
  -e HOME=/tmp \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  -w /work \
  "ghcr.io/librelane/librelane:$LIBRELANE_TAG" \
  "$@"
