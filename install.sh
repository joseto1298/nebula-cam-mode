#!/bin/bash
set -e

echo "=== Nebula Camera Mode - Instalacion ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOONRAKER_CUSTOM="$HOME/printer_data/moonraker/custom_components"
MOONRAKER_CONF="$HOME/printer_data/config/moonraker.conf"

# 1. Copiar plugin Moonraker
mkdir -p "$MOONRAKER_CUSTOM"
cp "$SCRIPT_DIR/moonraker_component/camera_mode.py" \
   "$MOONRAKER_CUSTOM/camera_mode.py"
echo "[OK] Plugin Moonraker copiado."

# 2. Registrar en moonraker.conf
if ! grep -q "^\[camera_mode\]" "$MOONRAKER_CONF" 2>/dev/null; then
    echo "" >> "$MOONRAKER_CONF"
    echo "[camera_mode]" >> "$MOONRAKER_CONF"
    echo "[OK] [camera_mode] anadido a moonraker.conf"
else
    echo "[OK] [camera_mode] ya existe en moonraker.conf"
fi

# 3. Symlink en components de Moonraker (para compatibilidad con legacy)
sudo ln -sf "$MOONRAKER_CUSTOM/camera_mode.py" \
            "/home/pi/moonraker/moonraker/components/camera_mode.py" 2>/dev/null || true

# 4. Sudoers para el script
sudo cp "$SCRIPT_DIR/010_nebula-cam-sudoers" /etc/sudoers.d/010_nebula-cam
sudo chmod 440 /etc/sudoers.d/010_nebula-cam
echo "[OK] Sudoers configurado."

# 5. Copiar navi.json (menu lateral en Mainsail)
mkdir -p "$HOME/printer_data/config/.theme"
cp "$SCRIPT_DIR/navi.json" "$HOME/printer_data/config/.theme/navi.json"
echo "[OK] navi.json copiado."

# 6. Anadir proxy inverso en nginx
NGINX_CONF=""
for f in /etc/nginx/sites-available/mainsail /etc/nginx/sites-available/mainsail-https \
          /etc/nginx/conf.d/mainsail.conf /etc/nginx/nginx.conf; do
    if [ -f "$f" ] && grep -q "server\s*{" "$f" 2>/dev/null; then
        NGINX_CONF="$f"
        break
    fi
done

if [ -n "$NGINX_CONF" ]; then
    if grep -q "nebula-camera-mode" "$NGINX_CONF" 2>/dev/null; then
        echo "[OK] Proxy inverso ya configurado en nginx."
    else
        sudo cp "$SCRIPT_DIR/nebula-camera-mode.nginx" /etc/nginx/snippets/nebula-camera-mode.conf
        # Insertar include dentro del primer server block, antes del cierre }
        sudo sed -i '0,/^}$/s|^}$|    include /etc/nginx/snippets/nebula-camera-mode.conf;\n}|' "$NGINX_CONF"
        sudo nginx -t && sudo systemctl reload nginx
        echo "[OK] Proxy inverso anadido a nginx."
    fi
else
    echo "[WARN] No se encontro config de nginx. Anade manualmente en tu server block:"
    cat "$SCRIPT_DIR/nebula-camera-mode.nginx"
fi

# 7. Copiar script principal
mkdir -p "$HOME/nebula-cam-mode"
cp "$SCRIPT_DIR/nebula_cam_mode.py" "$HOME/nebula-cam-mode/nebula_cam_mode.py"
chmod +x "$HOME/nebula-cam-mode/nebula_cam_mode.py"
echo "[OK] Script copiado."

# 8. Copiar configs de Klipper (debes importarlos manualmente)
mkdir -p "$HOME/printer_data/config"
cp "$SCRIPT_DIR/camera_macros.cfg" "$HOME/printer_data/config/camera_macros.cfg"
cp "$SCRIPT_DIR/shell_command_additions.cfg" "$HOME/printer_data/config/shell_command_additions.cfg"
echo "[OK] Configs de Klipper copiados."

# 9. Reiniciar Moonraker
sudo systemctl restart moonraker 2>/dev/null || echo "[WARN] No se pudo reiniciar Moonraker."
echo ""
echo "=== Instalacion completada ==="
echo ""
echo "IMPORTANTE: Anade estos includes en tu printer.cfg:"
echo "  [include camera_macros.cfg]"
echo "  [include shell_command_additions.cfg]"
echo ""
echo "Luego:"
echo "  - Refresca Mainsail (F5)"
echo "  - Veras 'CAM MODE' en el menu lateral"
echo "  - Abrelo para cambiar entre DAY/NIGHT/AUTO"
