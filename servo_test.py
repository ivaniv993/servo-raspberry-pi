#!/usr/bin/env python3
"""Minimal signal check for both servo pins. Run: python3 check_pins.py"""
import time, lgpio#!/usr/bin/env python3
"""Minimal signal check for both servo pins. Run: python3 check_pins.py"""
import time, lgpio

PAN_PIN, TILT_PIN, FREQ = 18, 13, 50

def angle_to_duty(a):
    return (0.5 + 2.0 * a / 180.0) / 20.0 * 100.0

h = lgpio.gpiochip_open(0)
for pin in (PAN_PIN, TILT_PIN):
    lgpio.gpio_claim_output(h, pin)

try:
    for name, pin in (("PAN/GPIO18", PAN_PIN), ("TILT/GPIO13", TILT_PIN)):
        print(f"{name}: sweeping 0 -> 90 -> 180")
        for a in (0, 90, 180, 90):
            duty = angle_to_duty(a)
            lgpio.tx_pwm(h, pin, FREQ, duty)
            print(f"  {a:3d} deg  pulse={duty/100*20:.2f} ms  duty={duty:.2f}%")
            time.sleep(0.8)
        lgpio.tx_pwm(h, pin, 0, 0)
finally:
    lgpio.tx_pwm(h, PAN_PIN, 0, 0)
    lgpio.tx_pwm(h, TILT_PIN, 0, 0)
    lgpio.gpiochip_close(h)
    print("Done, PWM stopped.")

PAN_PIN, TILT_PIN, FREQ = 18, 13, 50

def angle_to_duty(a):
    return (0.5 + 2.0 * a / 180.0) / 20.0 * 100.0

h = lgpio.gpiochip_open(0)
for pin in (PAN_PIN, TILT_PIN):
    lgpio.gpio_claim_output(h, pin)

try:
    for name, pin in (("PAN/GPIO18", PAN_PIN), ("TILT/GPIO13", TILT_PIN)):
        print(f"{name}: sweeping 0 -> 90 -> 180")
        for a in (0, 90, 180, 90):
            duty = angle_to_duty(a)
            lgpio.tx_pwm(h, pin, FREQ, duty)
            print(f"  {a:3d} deg  pulse={duty/100*20:.2f} ms  duty={duty:.2f}%")
            time.sleep(0.8)
        lgpio.tx_pwm(h, pin, 0, 0)
finally:
    lgpio.tx_pwm(h, PAN_PIN, 0, 0)
    lgpio.tx_pwm(h, TILT_PIN, 0, 0)
    lgpio.gpiochip_close(h)
    print("Done, PWM stopped.")
