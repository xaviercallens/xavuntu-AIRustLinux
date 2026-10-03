#!/usr/bin/env bash
# scripts/launch_gnome_cyberpunk_desktop.sh — GNOME Flashback & Cyberpunk Neon Display Session on DISPLAY=:1

set -e

echo "[1/6] Stopping previous display sessions on DISPLAY=:1..."
pkill -f "Xvfb :1" 2>/dev/null || true
pkill -f "x11vnc.*5901" 2>/dev/null || true
pkill -f "websockify.*6080" 2>/dev/null || true
pkill -f "gwaya_ai_hud.py" 2>/dev/null || true
pkill -f "gnome-session" 2>/dev/null || true
pkill -f "xfce4-session" 2>/dev/null || true
sleep 2

echo "[2/6] Starting Xvfb virtual framebuffer on :1 (1920x1080x24)..."
Xvfb :1 -screen 0 1920x1080x24 -nolisten tcp +extension GLX +render -noreset &
sleep 2

export DISPLAY=:1
export LIBGL_ALWAYS_SOFTWARE=1
export GTK_THEME=materia-cyberpunk-neon
export GDK_BACKEND=x11
export XDG_CURRENT_DESKTOP=GNOME-Flashback:GNOME
export XDG_MENU_PREFIX=gnome-flashback-

echo "[3/6] Starting GNOME Flashback Desktop Session..."
# Launch GNOME Flashback session with metacity and software rasterizer
dbus-launch --exit-with-session /usr/libexec/gnome-flashback-metacity &
sleep 4

# Apply Cyberpunk Neon theme and wallpaper
gsettings set org.gnome.desktop.interface gtk-theme "materia-cyberpunk-neon" 2>/dev/null || true
gsettings set org.gnome.desktop.interface color-scheme "prefer-dark" 2>/dev/null || true
gsettings set org.gnome.desktop.wm.preferences theme "materia-cyberpunk-neon" 2>/dev/null || true
gsettings set org.gnome.metacity theme "materia-cyberpunk-neon" 2>/dev/null || true

if [ -f /usr/share/backgrounds/xavuntu_kal.jpg ]; then
    feh --bg-fill /usr/share/backgrounds/xavuntu_kal.jpg 2>/dev/null || \
    gsettings set org.gnome.desktop.background picture-uri "file:///usr/share/backgrounds/xavuntu_kal.jpg" 2>/dev/null || true
fi

echo "[4/6] Starting x11vnc server (Port 5901)..."
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -shared -rfbport 5901 -bg -o /var/log/x11vnc.log 2>/dev/null || \
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -shared -rfbport 5901 &
sleep 1

echo "[5/6] Starting noVNC HTML5 WebSocket Proxy (Port 6080)..."
if [ -d /usr/share/novnc ]; then
    websockify --web /usr/share/novnc 6080 localhost:5901 &
elif [ -d /opt/noVNC ]; then
    websockify --web /opt/noVNC 6080 localhost:5901 &
fi
sleep 1

echo "[6/6] Launching KAL 9000 // GWAYA v3.8 AI & Cyber HUD Widget..."
python3 /usr/local/bin/gwaya_ai_hud.py &
sleep 2

echo "✓ GNOME Cyberpunk Neon Session active on DISPLAY=:1 (VNC 5901, noVNC 6080)."
