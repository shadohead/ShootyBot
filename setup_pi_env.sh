#!/bin/bash
# setup_pi_env.sh — Provision a Raspberry Pi to run ShootyBot WITHOUT ever
# compiling Python dependencies from source.
#
# WHY THIS EXISTS
# ---------------
# Production runs on a low-RAM Pi (~921 MiB) on Raspberry Pi OS *Bullseye*
# (glibc 2.31). If pip ever falls back to building a native package
# (numpy / matplotlib / contourpy …) from source, the compile exhausts memory
# and the kernel OOM-killer hangs the whole box — it has to be physically
# power-cycled. (This is exactly what took the bot down on 2026-06-15.)
#
# Two things must be true to avoid that:
#   1. pip must use PREBUILT wheels (piwheels) and never compile the heavy
#      native packages.
#   2. The venv must be built on Bullseye's NATIVE Python 3.9. piwheels' cp311
#      wheels are built on Bookworm (glibc 2.34+) and fail to import on
#      Bullseye ("GLIBC_2.34 not found"), which is what forces the source
#      builds in the first place. On 3.9, pip auto-resolves to the newest
#      3.9-compatible versions (matplotlib 3.9.x / numpy 2.0.x), all as wheels.
#
# This script is idempotent — safe to re-run.
#   Usage:  sudo ./setup_pi_env.sh
#   Then:   sudo systemctl restart shootybot.service
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo:  sudo ./setup_pi_env.sh"
    exit 1
fi

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${SUDO_USER:-$(whoami)}"     # venv should be owned by the bot user, not root
PYTHON="${PYTHON:-python3.9}"          # Bullseye's native interpreter
SWAP_MB="${SWAP_MB:-1024}"

echo "==> 1/4  Configure pip to use prebuilt wheels (piwheels), never source builds"
cp -n /etc/pip.conf /etc/pip.conf.bak 2>/dev/null || true
cat > /etc/pip.conf <<'PIPCONF'
[global]
# piwheels: prebuilt ARM wheels for Raspberry Pi OS.
extra-index-url=https://www.piwheels.org/simple
# Prefer wheels everywhere; REQUIRE them for the heavy native packages so pip
# errors loudly instead of attempting a from-source build (which OOM-freezes a
# low-RAM Pi). only-binary excludes sdists for these names entirely.
prefer-binary=true
only-binary=numpy,scipy,pandas,matplotlib,contourpy,kiwisolver,pillow,fonttools
PIPCONF
echo "    wrote /etc/pip.conf"

echo "==> 2/4  Ensure swap is at least ${SWAP_MB} MB (OOM safety net)"
if [ -f /etc/dphys-swapfile ]; then
    cp -n /etc/dphys-swapfile /etc/dphys-swapfile.bak 2>/dev/null || true
    sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=${SWAP_MB}/" /etc/dphys-swapfile
    dphys-swapfile swapoff || true
    dphys-swapfile setup
    dphys-swapfile swapon
    free -h | awk 'NR==1 || /Swap/'
else
    echo "    (dphys-swapfile not present; skipping swap config)"
fi

echo "==> 3/4  Install system libraries the numpy/matplotlib wheels link against"
apt-get update -qq || true
apt-get install -y libopenblas0 libgfortran5

echo "==> 4/4  (Re)build the virtualenv on ${PYTHON}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "    ERROR: $PYTHON not found. Install it with:"
    echo "           sudo apt-get install -y python3.9 python3.9-venv"
    exit 1
fi
cd "$BOT_DIR"
if [ -d venv ] && ! venv/bin/python --version 2>/dev/null | grep -q " 3.9"; then
    echo "    existing venv is not Python 3.9 — backing it up to venv.bak"
    rm -rf venv.bak
    mv venv venv.bak
fi
if [ ! -d venv ]; then
    sudo -u "$RUN_USER" "$PYTHON" -m venv venv
    echo "    created venv with $($PYTHON --version)"
fi
sudo -u "$RUN_USER" venv/bin/pip install --upgrade pip setuptools wheel
sudo -u "$RUN_USER" venv/bin/pip install -r requirements.txt --upgrade

echo "==> Verify numpy + matplotlib import and render (must NOT have compiled)"
sudo -u "$RUN_USER" venv/bin/python - <<'PY'
import io, numpy, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig = plt.figure(); fig.savefig(io.BytesIO(), format="png"); plt.close(fig)
print("OK  numpy", numpy.__version__, "| matplotlib", matplotlib.__version__)
PY

echo
echo "Done. Start/restart the bot with:  sudo systemctl restart shootybot.service"
