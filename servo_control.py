#!/usr/bin/env python3
"""
SG90 keyboard control for Raspberry Pi 5 (lgpio backend).
Left/Right arrows: -10/+10 degrees. Q or Ctrl+C: exit.

Install: sudo apt install python3-lgpio
Signal pin: GPIO18 (physical pin 12)
Log file: servo.log (also printed to console)
"""

import sys
import termios
import tty
import select
import logging
import lgpio

SERVO_PIN = 18
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


def main():
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, SERVO_PIN)

    angle = 90
    duty = angle_to_duty(angle)
    lgpio.tx_pwm(h, SERVO_PIN, FREQ, duty)

    log.info("Started. GPIO%d, %d Hz, step %d deg", SERVO_PIN, FREQ, STEP)
    log.info("Init: angle=%d deg, pulse=%.2f ms, duty=%.2f%%",
             angle, duty / 100.0 * 20.0, duty)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = read_key()
            if key is None:
                continue
            if key in ('q', 'Q', '\x03'):
                log.info("Exit key pressed")
                break
            if key == 'RIGHT':
                new = min(ANGLE_MAX, angle + STEP)
            elif key == 'LEFT':
                new = max(ANGLE_MIN, angle - STEP)
            else:
                log.debug("Ignored key: %r", key)
                continue

            if new != angle:
                duty = angle_to_duty(new)
                lgpio.tx_pwm(h, SERVO_PIN, FREQ, duty)
                log.info("%-5s | %3d -> %3d deg | pulse=%.2f ms | duty=%.2f%%",
                         key, angle, new, duty / 100.0 * 20.0, duty)
                angle = new
            else:
                limit = ANGLE_MAX if key == 'RIGHT' else ANGLE_MIN
                log.warning("%-5s | limit reached, staying at %d deg (max %d)",
                            key, angle, limit)
    except KeyboardInterrupt:
        log.info("Interrupted by Ctrl+C")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        lgpio.tx_pwm(h, SERVO_PIN, 0, 0)
        lgpio.gpiochip_close(h)
        log.info("PWM stopped, GPIO released. Final angle: %d deg", angle)


if __name__ == '__main__':
    main()
