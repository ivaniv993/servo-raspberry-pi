#!/usr/bin/env python3
"""
SG90 keyboard control for Raspberry Pi 5 (lgpio backend).
Left/Right arrows: -10/+10 degrees. Q or Ctrl+C: exit.

Install: sudo apt install python3-lgpio
Signal pin: GPIO18 (physical pin 12)
"""

import sys
import termios
import tty
import select
import lgpio

SERVO_PIN = 18
FREQ = 50
STEP = 10
ANGLE_MIN = 0
ANGLE_MAX = 180
PULSE_MIN = 0.5   # ms at 0 deg
PULSE_MAX = 2.5   # ms at 180 deg


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
    lgpio.tx_pwm(h, SERVO_PIN, FREQ, angle_to_duty(angle))
    print(f"Servo at {angle}\u00b0. Arrows to move, Q to quit.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = read_key()
            if key is None:
                continue
            if key in ('q', 'Q', '\x03'):
                break
            if key == 'RIGHT':
                new = min(ANGLE_MAX, angle + STEP)
            elif key == 'LEFT':
                new = max(ANGLE_MIN, angle - STEP)
            else:
                continue
            if new != angle:
                angle = new
                lgpio.tx_pwm(h, SERVO_PIN, FREQ, angle_to_duty(angle))
                print(f"\rAngle: {angle:3d}\u00b0   ", end='', flush=True)
            else:
                print(f"\rAngle: {angle:3d}\u00b0 (limit)", end='', flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        lgpio.tx_pwm(h, SERVO_PIN, 0, 0)
        lgpio.gpiochip_close(h)
        print("\nStopped.")


if __name__ == '__main__':
    main()
