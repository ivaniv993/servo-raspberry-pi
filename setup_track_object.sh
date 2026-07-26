#!/usr/bin/env bash
#
# One-time setup for track_object.py on Raspberry Pi 5 (Raspberry Pi OS Bookworm).
#
# Run this ONCE:
#   bash setup_track_object.sh
#
# After that, every time you want to run the tracker, just do:
#   source ~/envs/track/bin/activate
#   python track_object.py --dry-run
#
# Why you kept "reinstalling": Raspberry Pi OS Bookworm marks the system
# Python as "externally managed" (PEP 668). A bare `pip install ultralytics`
# either refuses to run, or if forced with --break-system-packages, gets
# wiped out the next time you `sudo apt upgrade`. The fix is to install
# everything into one persistent virtual environment (a folder of files)
# that apt never touches and that survives reboots. As long as you don't
# reflash the SD card, this venv stays installed forever.

set -euo pipefail

VENV_DIR="$HOME/envs/track"

echo "== 1/4: Updating apt and installing system dependencies =="
sudo apt update

# Installed one-by-one (not all in one `apt install`) so that a single
# package being renamed/removed in your OS version (e.g. libatlas-base-dev
# was dropped from newer Debian/Raspberry Pi OS repos) doesn't abort the
# whole setup. Any package that fails to install just prints a warning.
SYSTEM_PACKAGES=(
    python3-venv python3-pip python3-dev
    python3-lgpio
    libopenjp2-7 libopenblas-dev
    ffmpeg libgl1 libgtk-3-0
)
for pkg in "${SYSTEM_PACKAGES[@]}"; do
    if ! sudo apt install -y "$pkg"; then
        echo "WARNING: failed to install '$pkg' (may not exist on your OS version) - continuing"
    fi
done

echo "== 2/4: Creating persistent virtual environment at $VENV_DIR =="
# --system-site-packages lets the venv reuse apt's python3-lgpio (GPIO access
# needs system-level permissions/libraries that plain pip can't provide well).
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "Venv already exists, reusing it."
fi

echo "== 3/4: Installing Python packages into the venv =="
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install ultralytics opencv-python

echo "== 4/4: Verifying =="
python -c "import cv2, lgpio; from ultralytics import YOLO; print('OK: opencv', cv2.__version__, '| lgpio and ultralytics import fine')"

deactivate

echo
echo "Setup complete. From now on, in any new terminal, run:"
echo "  source $VENV_DIR/bin/activate"
echo "  python track_object.py --dry-run"
echo
echo "You do NOT need to reinstall packages again unless you reflash the SD card."
