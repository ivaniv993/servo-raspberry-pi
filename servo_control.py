#!/usr/bin/env python3
"""
Dual SG90 keyboard control for Raspberry Pi 5 (lgpio backend).
Left/Right arrows: pan servo -10/+10 degrees.
Up/Down arrows:    tilt servo +10/-10 degrees.
Q or Ctrl+C: exit.

Install: sudo apt install python3-lgpio

Wiring (BCM numbering):
  Pan servo  (left/right) signal -> GPIO18, physical pin 12
  Tilt servo (up/down)    signal -> GPIO13, physical pin 33
  Both servo grounds      -> Pi GND (e.g. physical pin 6) AND external supply GND (common ground)
  Both servo power (red)  -> external 5-6V supply (+), NOT the Pi's 5V pin

Log file: servo.log (also printed to console)
"""

import sys
import termios
import tty
import select
import logging
import lgpio

PAN_PIN = 18    # left/right, physical pin 12
TILT_PIN = 13   # up/down,    physical pin 33
FREQ = 50
STEP = 10
ANGLE_MIN = 0
ANGLE_MAX = 180
PULSE_MIN = 0.5   # ms at 0 deg
PULSE_MAX = 2.5   # ms at 180 deg
LOG_FILE = "servo.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("servo")


def angle_to_duty(angle):
    """Convert angle to duty cycle percent for a 20 ms period."""
    pulse_ms = PULSE_MIN + (PULSE_MAX - PULSE_MIN) * angle / 180.0
    return pulse_ms / 20.0 * 100.0


def read_key(timeout=0.1):
    """Non-blocking read of a single key; decodes arrow escape sequences."""
    if not select.select([sys.stdin], [], [], timeout)[0]:
        return None
    ch = sys.stdin.read(1)
    if ch != '\x1b':
        return ch
    if not select.select([sys.stdin], [], [], 0.05)[0]:
        return '\x1b'
    seq = sys.stdin.read(2)
    return {'[C': 'RIGHT', '[D': 'LEFT', '[A': 'UP', '[B': 'DOWN'}.get(seq)


def set_angle(h, pin, angle):
    """Apply an angle to a servo and return its duty cycle."""
    duty = angle_to_duty(angle)
    lgpio.tx_pwm(h, pin, FREQ, duty)
    return duty


def main():
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PAN_PIN)
    lgpio.gpio_claim_output(h, TILT_PIN)

    # axis -> [pin, current angle, human name]
    axes = {
        'pan':  {'pin': PAN_PIN,  'angle': 90, 'name': 'PAN '},
        'tilt': {'pin': TILT_PIN, 'angle': 90, 'name': 'TILT'},
    }

    for ax in axes.values():
        duty = set_angle(h, ax['pin'], ax['angle'])
        log.info("Init: %s angle=%d deg, pulse=%.2f ms, duty=%.2f%%",
                 ax['name'], ax['angle'], duty / 100.0 * 20.0, duty)

    log.info("Started. PAN=GPIO%d TILT=GPIO%d, %d Hz, step %d deg",
             PAN_PIN, TILT_PIN, FREQ, STEP)
    log.info("Keys: LEFT/RIGHT = pan, UP/DOWN = tilt, Q = quit")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
