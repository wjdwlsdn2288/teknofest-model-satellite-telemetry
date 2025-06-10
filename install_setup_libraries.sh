#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Optional: log output to a file
exec > >(tee -i script.log)
exec 2>&1

echo ">>> Installing required packages..."
sudo python3 -m pip install \
  asyncio \
  adafruit-circuitpython-bmp3xx \
  adafruit-circuitpython-bno055 \
  board \
  pigpio \
  pytz \
  pyserial \
  websockets \
  adafruit-circuitpython-ds3231 \
  adafruit-circuitpython-tmp117 \
  Flask \
  picamera

echo ">>> Uninstalling conflicting or unnecessary packages..."
sudo python3 -m pip uninstall -y \
  adafruit-circuitpython-busdevice \
  adafruit-circuitpython-requests \
  adafruit-circuitpython-typing \
  adafruit-blinka \
  numpy \
  pyftdi \
  pyserial \
  pyusb \
  rpi-ws281x \
  sysv-ipc \
  typing-extensions

echo ">>> Reinstalling cleaned packages..."
sudo python3 -m pip install \
  adafruit-circuitpython-busdevice \
  adafruit-circuitpython-requests \
  adafruit-circuitpython-typing \
  adafruit-blinka \
  numpy \
  pyftdi \
  pyserial \
  pyusb \
  rpi-ws281x \
  sysv-ipc \
  typing-extensions

echo ">>> Done."