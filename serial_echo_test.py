#!/usr/bin/env python3
"""Quick serial smoke test for CalSci hybrid bridge.

Usage:
  python serial_echo_test.py --port /dev/ttyACM0 --baud 115200
"""

import argparse
import time

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    token = "TEST_%d" % int(time.time() * 1000)
    print("Opening", args.port, "at", args.baud)
    ser = serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=None)
    try:
        ser.reset_input_buffer()
        try:
            ser.reset_output_buffer()
        except Exception:
            pass

        line = "PING:%s\n" % token
        ser.write(line.encode("ascii"))
        print("TX:", line.strip())

        deadline = time.time() + args.timeout
        got_echo = False
        got_state = False

        while time.time() < deadline:
            rx = ser.readline().decode("utf-8", errors="ignore").strip()
            if not rx:
                continue
            print("RX:", rx)
            if ("ECHO:%s" % token) in rx or ("PING:%s" % token) in rx:
                got_echo = True
            if rx.startswith("STATE:"):
                got_state = True
            if got_echo and got_state:
                break

        if not got_echo:
            print("FAIL: No ECHO response")
            return 1
        if not got_state:
            print("WARN: Echo OK, but no STATE frame observed in timeout")
            return 0

        print("PASS: Echo + STATE received")
        return 0
    finally:
        ser.close()


if __name__ == "__main__":
    raise SystemExit(main())
