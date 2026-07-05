# Nebula Cam Mode

Control de modo IR para la cámara **Creality Nebula Camera** en el ecosistema Klipper/Moonraker/Mainsail.

Controla el filtro IR (día/noche/auto), brillo, contraste, exposición y demás controles V4L2 mediante una interfaz web en Mainsail o macros G-code desde Klipper.

## Instalación

```bash
git clone https://github.com/tu-usuario/nebula-cam-mode.git ~/nebula-cam-mode
cd ~/nebula-cam-mode
./install.sh
```

Luego añadir en `printer.cfg`:

```ini
[include camera_macros.cfg]
[include shell_command_additions.cfg]
```

## Uso

### CLI

```bash
python3 nebula_cam_mode.py day|night|auto        # Cambiar modo IR
python3 nebula_cam_mode.py status -j              # Estado completo en JSON
python3 nebula_cam_mode.py set brightness 100     # Ajustar control V4L2
python3 nebula_cam_mode.py expose manual 500      # Exposición manual
python3 nebula_cam_mode.py brightness_up          # Brillo +10
python3 nebula_cam_mode.py --device /dev/video2 status
```

### Web (Mainsail)

Tras la instalación, aparece "CAM MODE" en el menú lateral. Panel con botones DAY/NIGHT/AUTO y tabla de controles V4L2.

### G-code (Klipper)

| Macro | Descripción |
|---|---|
| `CAMERA_DAY` | Modo día |
| `CAMERA_NIGHT` | Modo noche |
| `CAMERA_AUTO_CAM` | Modo auto |
| `CAMERA_BRIGHTNESS_UP` | Brillo +10 |
| `CAMERA_BRIGHTNESS_DOWN` | Brillo -10 |
| `CAMERA_EXPOSURE_MANUAL EXP_VAL=500` | Exposición manual |
| `CAMERA_EXPOSURE_AUTO` | Exposición automática |
| `CAMERA_STATUS` | Estado completo |
| `CAMERA_INFO` | Info de firmware |

## Arquitectura

- `nebula_cam_mode.py` — Script CLI que controla la cámara via UVC Extension Unit + v4l2-ctl
- `moonraker_component/camera_mode.py` — Plugin Moonraker asíncrono (9 endpoints HTTP)
- `camera_macros.cfg` — Macros G-code para Klipper
- `shell_command_additions.cfg` — Shell commands que conectan macros con el script
- `install.sh` — Script de instalación para Raspberry Pi

Los perfiles de brillo/contraste por modo IR se guardan en `~/.nebula_cam_profiles.json`.
