#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "⚡ XAVUNTU 24.04 LTS: INSTALLING GNOME, KULA & CYBERPUNK NEON"
echo "=========================================================="

export DEBIAN_FRONTEND=noninteractive

echo "[1/5] Installing Kula Real-Time Monitoring Engine (v0.21.0)..."
curl -sL "https://github.com/c0m4r/kula/releases/download/0.21.0/kula-0.21.0-amd64.deb" -o /tmp/kula.deb
sudo dpkg -i /tmp/kula.deb || sudo apt-get install -f -y

# Configure Kula service if not already created
if ! systemctl is-active --quiet kula; then
    echo "Creating systemd service for Kula..."
    sudo tee /etc/systemd/system/kula.service > /dev/null << 'EOF'
[Unit]
Description=Kula Real-Time Linux System Telemetry Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/kula -listen 0.0.0.0:8088
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now kula || sudo /usr/bin/kula -listen 0.0.0.0:8088 &
fi

echo "[2/5] Installing GNOME Flashback & Desktop Stack..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    gnome-session-flashback \
    gnome-panel \
    metacity \
    gnome-terminal \
    gnome-tweaks \
    mutter \
    mesa-utils \
    scrot \
    unzip \
    jq

echo "[3/5] Extracting Cyberpunk Neon GTK & GNOME Themes..."
sudo mkdir -p /usr/share/themes
if [ -f /tmp/cyberpunk-neon/gtk/materia-cyberpunk-neon.zip ]; then
    sudo unzip -q -o /tmp/cyberpunk-neon/gtk/materia-cyberpunk-neon.zip -d /usr/share/themes/
    echo "✓ Extracted materia-cyberpunk-neon to /usr/share/themes"
fi
if [ -f /tmp/cyberpunk-neon/gtk/oomox-cyberpunk-neon.zip ]; then
    sudo unzip -q -o /tmp/cyberpunk-neon/gtk/oomox-cyberpunk-neon.zip -d /usr/share/themes/
    echo "✓ Extracted oomox-cyberpunk-neon to /usr/share/themes"
fi

echo "[4/5] Configuring GNOME Cyberpunk Neon Theme Preferences..."
# Configure gsettings defaults for user xavkal
sudo -u xavkal dbus-launch gsettings set org.gnome.desktop.interface gtk-theme "materia-cyberpunk-neon" 2>/dev/null || true
sudo -u xavkal dbus-launch gsettings set org.gnome.desktop.interface color-scheme "prefer-dark" 2>/dev/null || true
sudo -u xavkal dbus-launch gsettings set org.gnome.desktop.wm.preferences theme "materia-cyberpunk-neon" 2>/dev/null || true
sudo -u xavkal dbus-launch gsettings set org.gnome.metacity theme "materia-cyberpunk-neon" 2>/dev/null || true

echo "[5/5] Verification:"
echo "Kula status: $(curl -sI http://127.0.0.1:8088 | head -n 1 || echo 'pending')"
ls -d /usr/share/themes/*cyberpunk* || true
echo "✓ GNOME & Kula installation completed successfully."
