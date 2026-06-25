# Nebula Cam Mode — Agent guide

## Project structure

```
nebula_cam_mode.py              # CLI entrypoint: controls IR mode via UVC ioctls + v4l2-ctl
moonraker_component/
  camera_mode.py                # Moonraker plugin: 9 HTTP endpoints, calls nebula_cam_mode.py
camera_macros.cfg               # Klipper G-code macros (day/night/auto/brightness/exposure)
shell_command_additions.cfg     # Klipper shell_command definitions (bridges macros → nebula_cam_mode.py)
install.sh                      # Deploy to Klipper/Moonraker/Mainsail on Raspberry Pi
010_nebula-cam-sudoers          # Sudoers entry for pi user
nebula-camera-mode.nginx        # Nginx reverse-proxy snippet for Moonraker
navi.json                       # Mainsail sidebar menu entry
```

## Key architecture

- **No package manager, no tests, no CI.** Deployed via `install.sh` on a Raspberry Pi running Klipper.
- `nebula_cam_mode.py` is the single source of truth for camera control. It uses `--device <path>` or auto-detects via `/dev/v4l/by-id/usb-UnionImage_Co*`.
- `moonraker_component/camera_mode.py` is an async Moonraker plugin that shells out to `nebula_cam_mode.py -j` for all operations. Panel HTML is rendered server-side with status data.
- Profiles (brightness/contrast/etc per IR mode) are stored in `~/.nebula_cam_profiles.json`.

## Commands

```bash
# All camera control goes through nebula_cam_mode.py
python3 nebula_cam_mode.py status -j          # JSON status
python3 nebula_cam_mode.py day|night|auto      # IR mode
python3 nebula_cam_mode.py set brightness 100   # V4L2 control (auto-saved to profile)
python3 nebula_cam_mode.py get brightness       # Read V4L2 control
python3 nebula_cam_mode.py expose manual 500    # Manual exposure
python3 nebula_cam_mode.py brightness_up        # +10 (also brightness_down)
python3 nebula_cam_mode.py --device /dev/video2 status
```

## Device propagation pattern

`v4l2_get()` and `v4l2_set()` accept an optional `dev` parameter. If omitted, they fall back to `CURRENT_DEVICE` global, then `/dev/video0`. All command functions that receive a `dev` argument pass it explicitly. `main()` sets `CURRENT_DEVICE` once after auto-detect so all downstream calls (including `cmd_brightness`, `cmd_set_ctrl`) use the correct device.

## Klipper integration

- `camera_macros.cfg` defines G-code macros, each calling a shell command from `shell_command_additions.cfg`
- Each shell command runs `sudo python3 ~/nebula-cam-mode/nebula_cam_mode.py <action>`
- Add `[include camera_macros.cfg]` and `[include shell_command_additions.cfg]` to `printer.cfg`
- The Moonraker plugin listens at `/machine/camera_mode/{panel,status,info,day,night,auto,expose,set,get}`

## Conventions

- Always pass `-j` flag when calling the script from another program (Moonraker component, shell commands)
- JSON output from the script is the contract between layers
- The `010_nebula-cam-sudoers` file assumes user `pi` — adjust if deploying under a different user
- Values for `auto_exposure`: `0` = auto, `1` = manual (UVC convention, may vary per driver)

## Gotchas

- `install.sh` line 27 symlinks into `/home/pi/moonraker/moonraker/components/` — fails if Moonraker is installed elsewhere
- Sudoers file uses `/home/pi/` (sudoers does not expand `~`)
- The Moonraker component panel JS silences `refresh()` errors — check Moonraker logs if the panel is blank
