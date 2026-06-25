#!/usr/bin/env python3
"""
Creality Nebula Camera (NC01) - Complete Control Tool
Controls IR mode via UVC Extension Unit + all V4L2 controls.

Usage:
  nebula_cam_mode.py status                              # Full camera status (JSON if -j)
  nebula_cam_mode.py day|night|auto                      # Set IR mode (backward compat)
  nebula_cam_mode.py info                                # Firmware & camera info
  nebula_cam_mode.py set <control> <value>                # Set any V4L2 control
  nebula_cam_mode.py get <control>                        # Get any V4L2 control
  nebula_cam_mode.py expose auto|manual [exposure_val]   # Exposure mode
  nebula_cam_mode.py <device> day|night|auto|status       # Explicit device (backward compat)
"""

import glob
import os
import sys
import json
import time
import fcntl
import ctypes
import subprocess

CONFIG_FILE = os.path.expanduser("~/.nebula_cam_profiles.json")
CURRENT_DEVICE = None

# UVC constants
UVC_GET_CUR = 0x81
UVC_SET_CUR = 0x01
UVCIOC_CTRL_QUERY = 0xC0107521
UVC_GET_LEN = 0x85

# Extension unit config
UNIT_ID = 6
SEL_MODE = 16
SEL_FIRMWARE = 15
CONTROL_SIZE = 60

IR_MODES = {
    "day":   0x00,
    "night": 0x01,
    "auto":  0x02,
}
IR_MODE_NAMES = {
    0x00: "DAY (color, IR-cut ON, IR LEDs OFF)",
    0x01: "NIGHT (grayscale, IR-cut OFF, IR LEDs ON)",
    0x02: "AUTO (sensor-based switching)",
}
IR_MODE_SHORT = {0x00: "day", 0x01: "night", 0x02: "auto"}

V4L2_CTRLS = {
    "brightness":             {"min": 50,  "max": 160, "default": 128},
    "contrast":               {"min": 50,  "max": 160, "default": 128},
    "saturation":             {"min": 50,  "max": 160, "default": 128},
    "hue":                    {"min": 50,  "max": 160, "default": 128},
    "gamma":                  {"min": 0,   "max": 800, "default": 400},
    "sharpness":              {"min": 50,  "max": 160, "default": 128},
    "backlight_compensation": {"min": 0,   "max": 4,   "default": 0},
    "exposure_time_absolute": {"min": 1,   "max": 1000, "default": 156},
    "focus_absolute":         {"min": 0,   "max": 1000, "default": 500},
    "zoom_absolute":          {"min": 100, "max": 200,  "default": 100},
    "white_balance_temperature": {"min": 300, "max": 600, "default": 417},
}


class UvcXuControlQuery(ctypes.Structure):
    _fields_ = [
        ("unit", ctypes.c_uint8),
        ("selector", ctypes.c_uint8),
        ("query", ctypes.c_uint8),
        ("size", ctypes.c_uint16),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
    ]


def xu_get_cur(fd, unit, selector, size):
    buf = (ctypes.c_uint8 * size)()
    q = UvcXuControlQuery(unit, selector, UVC_GET_CUR, size, buf)
    fcntl.ioctl(fd, UVCIOC_CTRL_QUERY, q, True)
    return bytes(buf[:q.size])


def xu_set_cur(fd, unit, selector, data):
    size = len(data)
    buf = (ctypes.c_uint8 * size)(*data)
    q = UvcXuControlQuery(unit, selector, UVC_SET_CUR, size, buf)
    fcntl.ioctl(fd, UVCIOC_CTRL_QUERY, q, True)


def read_ir_mode(fd):
    raw = xu_get_cur(fd, UNIT_ID, SEL_MODE, CONTROL_SIZE)
    return raw[0] if raw else None


def set_ir_mode(fd, value):
    data = bytes([value]) + b'\x00' * (CONTROL_SIZE - 1)
    xu_set_cur(fd, UNIT_ID, SEL_MODE, list(data))
    val2 = read_ir_mode(fd)
    if val2 != value:
        xu_set_cur(fd, UNIT_ID, SEL_MODE, list(data))


def read_firmware(fd):
    raw = xu_get_cur(fd, UNIT_ID, SEL_FIRMWARE, CONTROL_SIZE)
    return raw.rstrip(b'\x00').decode('ascii', errors='replace') if raw else "unknown"


def auto_detect_device():
    matches = sorted(glob.glob("/dev/v4l/by-id/usb-UnionImage_Co*"))
    for m in matches:
        if "index0" in m:
            return os.path.realpath(m)
    if matches:
        return os.path.realpath(matches[0])
    return None


def load_profiles():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"day": {}, "night": {}}


def save_profiles(profiles):
    with open(CONFIG_FILE, "w") as f:
        json.dump(profiles, f, indent=2)


def profile_set_val(mode, control, value):
    profiles = load_profiles()
    profiles.setdefault(mode, {})[control] = value
    save_profiles(profiles)


def profile_apply(mode, retries=5, delay=1, dev=None):
    profiles = load_profiles()
    vals = profiles.get(mode, {})

    # Night defaults: lock exposure to prevent auto-exposure overriding brightness
    if mode == "night":
        if "exposure_time_absolute" not in vals:
            v4l2_set("auto_exposure", 1, dev)
            v4l2_set("exposure_time_absolute", 500, dev)
            time.sleep(0.5)

    for ctrl, val in vals.items():
        for attempt in range(retries):
            v4l2_set(ctrl, val, dev)
            time.sleep(0.2)
            readback = v4l2_get(ctrl, dev)
            if readback is not None and readback == val:
                break
            if attempt < retries - 1:
                time.sleep(delay)


def v4l2_get(control, dev=None):
    device = dev or CURRENT_DEVICE or "/dev/video0"
    r = subprocess.run(["v4l2-ctl", "-d", device, "-C", control],
                       capture_output=True, text=True, timeout=5)
    for line in r.stdout.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            parts = line.split(":", 1)
            val = parts[1].strip()
        else:
            val = line
        try:
            return int(val.split()[0])
        except (ValueError, IndexError):
            return val
    return None


def v4l2_set(control, value, dev=None):
    device = dev or CURRENT_DEVICE or "/dev/video0"
    r = subprocess.run(["v4l2-ctl", "-d", device, "-c", "%s=%s" % (control, value)],
                       capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return r.stderr.strip()
    return None


def get_full_status(dev):
    result = {"device": dev}
    fd = os.open(dev, os.O_RDWR)
    try:
        ir_val = read_ir_mode(fd)
        result["ir_mode"] = {"value": ir_val, "name": IR_MODE_NAMES.get(ir_val, "UNKNOWN"),
                             "short": IR_MODE_SHORT.get(ir_val, "unknown")}
        result["firmware"] = read_firmware(fd)
    finally:
        os.close(fd)

    for ctrl in V4L2_CTRLS:
        val = v4l2_get(ctrl, dev)
        if val is not None:
            result[ctrl] = val

    for bool_ctrl in ["white_balance_automatic", "focus_automatic_continuous"]:
        val = v4l2_get(bool_ctrl, dev)
        if val is not None:
            result[bool_ctrl] = bool(int(val)) if str(val).isdigit() else val

    ae = v4l2_get("auto_exposure", dev)
    result["auto_exposure"] = ae
    return result


def cmd_status(dev, json_output):
    status = get_full_status(dev)
    if json_output:
        print(json.dumps(status, indent=2))
        return

    print("=== Nebula Camera NC01 Status ===")
    print("Device:  %s" % status["device"])
    print("IR Mode: %s" % status["ir_mode"]["name"])
    print("Firmware: %s" % status["firmware"])
    print()
    print("--- V4L2 Controls ---")
    for ctrl in sorted(V4L2_CTRLS):
        if ctrl in status:
            val = status[ctrl]
            ctrl_info = V4L2_CTRLS[ctrl]
            print("  %-30s = %s  (range: %s..%s)" % (ctrl, val, ctrl_info["min"], ctrl_info["max"]))
    for bc in ["white_balance_automatic", "focus_automatic_continuous"]:
        if bc in status:
            print("  %-30s = %s" % (bc, status[bc]))
    print("  %-30s = %s" % ("auto_exposure", status.get("auto_exposure", "?")))


def cmd_info(dev, json_output):
    fd = os.open(dev, os.O_RDWR)
    try:
        fw = read_firmware(fd)
        ir_val = read_ir_mode(fd)
    finally:
        os.close(fd)

    if json_output:
        print(json.dumps({
            "device": dev,
            "firmware": fw,
            "ir_mode": ir_val,
            "ir_mode_name": IR_MODE_NAMES.get(ir_val, "UNKNOWN"),
        }, indent=2))
        return

    print("Device:  %s" % dev)
    print("Firmware: %s" % fw)
    print("IR Mode: %s" % IR_MODE_NAMES.get(ir_val, "UNKNOWN"))
    print()
    print("Supported resolutions:")
    for res in ["1920x1080", "1280x960", "1280x720", "800x600", "640x480", "640x360"]:
        print("  %s @ 30fps (MJPG, YUYV, NV12, H264)" % res)


def cmd_set_ir(dev, mode, json_output):
    fd = os.open(dev, os.O_RDWR)
    try:
        val = IR_MODES[mode]
        set_ir_mode(fd, val)
        confirmed = read_ir_mode(fd)
        if confirmed != val:
            time.sleep(0.5)
            set_ir_mode(fd, val)
            confirmed = read_ir_mode(fd)
    finally:
        os.close(fd)
            
    profile_apply(mode, dev=dev)
    if json_output:
        print(json.dumps({"action": "set_ir", "mode": mode, "value": val,
                          "confirmed": confirmed, "status": "ok" if confirmed == val else "mismatch"}))
        return
    if confirmed == val:
        print("IR mode set to %s (0x%02x) -> confirmed: %s" % (mode.upper(), val, IR_MODE_NAMES[confirmed]))
    else:
        print("WARNING: desired 0x%02x but readback 0x%02x" % (val, confirmed))


def get_current_ir_mode(dev=None):
    device = dev or CURRENT_DEVICE or auto_detect_device()
    if not device:
        return None
    fd = os.open(device, os.O_RDWR)
    try:
        val = read_ir_mode(fd)
        return IR_MODE_SHORT.get(val)
    finally:
        os.close(fd)


def cmd_set_ctrl(control, value, json_output, dev=None):
    err = v4l2_set(control, value, dev)
    if json_output:
        print(json.dumps({"action": "set", "control": control, "value": value,
                          "error": err, "status": "error" if err else "ok"}))
        return
    if err:
        print("Error setting %s=%s: %s" % (control, value, err))
    else:
        new_val = v4l2_get(control, dev)
        mode = get_current_ir_mode(dev)
        profile_set_val(mode, control, new_val)
        print("Set %s = %s  (readback: %s)  [saved to %s profile]" % (control, value, new_val, mode))


def cmd_get_ctrl(control, json_output):
    val = v4l2_get(control)
    if json_output:
        print(json.dumps({"control": control, "value": val}))
        return
    print("%s = %s" % (control, val))


def cmd_exposure(dev, mode, exp_val, json_output):
    if mode == "auto":
        err = v4l2_set("auto_exposure", 0, dev)
        if json_output:
            print(json.dumps({"action": "exposure", "mode": "auto", "error": err,
                              "status": "error" if err else "ok"}))
            return
        if err:
            print("Error: %s" % err)
        else:
            print("Exposure set to AUTO")
    elif mode == "manual":
        err = v4l2_set("auto_exposure", 1, dev)
        if err:
            if json_output:
                print(json.dumps({"action": "exposure", "mode": "manual", "error": err,
                                  "status": "error"}))
            else:
                print("Error: %s" % err)
            return
        if exp_val is not None:
            err2 = v4l2_set("exposure_time_absolute", exp_val, dev)
            if err2:
                if json_output:
                    print(json.dumps({"action": "exposure", "mode": "manual",
                                      "exposure_value": exp_val, "error": err2, "status": "error"}))
                else:
                    print("Error setting exposure: %s" % err2)
                return
        if json_output:
            result = {"action": "exposure", "mode": "manual", "status": "ok"}
            if exp_val is not None:
                result["exposure_value"] = exp_val
            print(json.dumps(result))
        else:
            msg = "Exposure set to MANUAL"
            if exp_val is not None:
                msg += " (exposure_time=%d)" % exp_val
            print(msg)


def cmd_profile(mode_arg, json_output):
    profiles = load_profiles()
    if mode_arg == "show":
        if json_output:
            print(json.dumps({"profiles": profiles}, indent=2))
            return
        for m in ("day", "night"):
            print("%s profile:" % m.upper())
            vals = profiles.get(m, {})
            if vals:
                for ctrl, val in sorted(vals.items()):
                    print("  %-30s = %s" % (ctrl, val))
            else:
                print("  (no saved values)")
            print()
        return

    if mode_arg in ("day", "night"):
        profiles[mode_arg] = {}
        save_profiles(profiles)
        if json_output:
            print(json.dumps({"action": "profile_reset", "mode": mode_arg}))
            return
        print("Profile reset for %s mode." % mode_arg)
        return

    print("Usage: profile show|day|night", file=sys.stderr)
    sys.exit(1)


def cmd_brightness(change, json_output):
    val = v4l2_get("brightness")
    if val is None or not isinstance(val, int):
        if json_output:
            print(json.dumps({"action": "brightness", "error": "cannot read current brightness"}))
            return
        print("Error: cannot read current brightness")
        return
    new_val = max(50, min(160, val + change))
    err = v4l2_set("brightness", new_val)
    if json_output:
        print(json.dumps({"action": "brightness", "change": change, "old": val, "new": new_val,
                          "error": err, "status": "error" if err else "ok"}))
        return
    if err:
        print("Error setting brightness: %s" % err)
    else:
        print("Brightness: %d -> %d (%s%d)" % (val, new_val, "+" if change >= 0 else "", change))


def print_usage(prog):
    print("Usage:")
    print("  %s status [-j]                # Full camera status" % prog)
    print("  %s day|night|auto [-j]        # Set IR mode" % prog)
    print("  %s info [-j]                  # Camera & firmware info" % prog)
    print("  %s set <ctrl> <val> [-j]      # Set V4L2 control (saves to current mode profile)" % prog)
    print("  %s get <ctrl> [-j]            # Get V4L2 control" % prog)
    print("  %s expose auto|manual [val] [-j]  # Exposure mode" % prog)
    print("  %s profile show               # Show saved profiles" % prog)
    print("  %s profile day|night          # Reset profile for a mode" % prog)
    print("  %s brightness_up              # Increase brightness by 10" % prog)
    print("  %s brightness_down            # Decrease brightness by 10" % prog)
    print("  %s <device> <action>          # Backward compat: explicit device" % prog)
    print("  [--device <path>]             # Specify camera device (default: auto-detect)")
    print()
    print("V4L2 controls: %s" % ", ".join(sorted(V4L2_CTRLS.keys())))
    print("               white_balance_automatic, focus_automatic_continuous")
    print("               auto_exposure, power_line_frequency")
    print()
    print("Profiles store brightness/contrast/etc per IR mode.")
    print("When switching day<->night, saved values are auto-applied.")
    print()
    print("Examples:")
    print("  %s night" % prog)
    print("  %s set brightness 100          # saved to night profile" % prog)
    print("  %s day                         # restores day brightness" % prog)
    print("  %s expose manual 500" % prog)
    print("  %s brightness_up" % prog)
    print("  %s --device /dev/video2 status" % prog)
    print("  %s /dev/video0 status" % prog)


def main():
    global CURRENT_DEVICE

    json_output = "-j" in sys.argv or "--json" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("-j", "--json")]

    if "--device" in args:
        idx = args.index("--device")
        if idx + 1 < len(args):
            CURRENT_DEVICE = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    if not args:
        print_usage(sys.argv[0])
        sys.exit(1)

    arg1 = args[0].lower()

    if not CURRENT_DEVICE:
        CURRENT_DEVICE = auto_detect_device()

    if arg1 in IR_MODES:
        dev = CURRENT_DEVICE
        if not dev:
            print("Error: no Nebula camera detected. Connect camera or specify device path.", file=sys.stderr)
            sys.exit(1)
        cmd_set_ir(dev, arg1, json_output)
        return

    if arg1 == "status":
        dev = CURRENT_DEVICE
        if not dev:
            print("Error: no Nebula camera detected.", file=sys.stderr)
            sys.exit(1)
        cmd_status(dev, json_output)
        return

    if arg1 == "info":
        dev = CURRENT_DEVICE
        if not dev:
            print("Error: no Nebula camera detected.", file=sys.stderr)
            sys.exit(1)
        cmd_info(dev, json_output)
        return

    if arg1 == "set":
        if len(args) < 3:
            print("Usage: %s set <control> <value>" % sys.argv[0])
            sys.exit(1)
        cmd_set_ctrl(args[1], args[2], json_output)
        return

    if arg1 == "get":
        if len(args) < 2:
            print("Usage: %s get <control>" % sys.argv[0])
            sys.exit(1)
        cmd_get_ctrl(args[1], json_output)
        return

    if arg1 == "expose":
        if len(args) < 2:
            print("Usage: %s expose auto|manual [exposure_value]" % sys.argv[0])
            sys.exit(1)
        mode = args[1].lower()
        if mode not in ("auto", "manual"):
            print("Invalid exposure mode: %s. Use 'auto' or 'manual'." % mode, file=sys.stderr)
            sys.exit(1)
        exp_val = int(args[2]) if len(args) > 2 else None
        dev = CURRENT_DEVICE
        if not dev:
            print("Error: no Nebula camera detected.", file=sys.stderr)
            sys.exit(1)
        cmd_exposure(dev, mode, exp_val, json_output)
        return

    if arg1 == "profile":
        if len(args) < 2:
            print("Usage: %s profile show|day|night" % sys.argv[0])
            sys.exit(1)
        cmd_profile(args[1], json_output)
        return

    if arg1 == "brightness_up":
        cmd_brightness(10, json_output)
        return

    if arg1 == "brightness_down":
        cmd_brightness(-10, json_output)
        return

    # Backward compat: explicit device path
    dev = arg1
    if not os.path.exists(dev):
        print("Error: device %s not found" % dev, file=sys.stderr)
        print_usage(sys.argv[0])
        sys.exit(1)
    action = args[1].lower() if len(args) > 1 else "status"

    if action in IR_MODES:
        cmd_set_ir(dev, action, json_output)
    elif action in ("status", "info"):
        cmd_status(dev, json_output) if action == "status" else cmd_info(dev, json_output)
    else:
        print("Unknown action: %s" % action, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
