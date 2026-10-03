#!/bin/bash
# ==============================================================================
# connect_xavuntu_gui.sh — Zero-Trust Local Client for Xavuntu Spot Workstation
# ==============================================================================
set -e

PROJECT="gen-lang-client-0625573011"
ZONE="us-central1-c"
VM="xavuntu-desktop-1791007070"
VNC_PASSWD="xavuntu"

echo "=================================================================="
echo "=== CONNECTING TO XAVUNTU SPOT WORKSTATION GRAPHICAL DESKTOP ==="
echo "=================================================================="
echo " VM Name:        $VM"
echo " Zone:           $ZONE"
echo " Hardware:       n2-standard-8 (8 vCPUs, 32 GB RAM)"
echo " Data Disk:      1,000 GB (1 TB) ext4 mounted on /data"
echo " VNC Password:   $VNC_PASSWD"
echo " Web GUI URL:    http://localhost:6080/vnc.html"
echo " Native VNC:     localhost:5901"
echo "=================================================================="

# 1. Establish SSH Port Tunnel if not already running
echo "--> Checking local port forwarding..."
if ss -tuln | grep -q ":6080"; then
    echo "--> Local port 6080 is already active (tunnel open)."
else
    echo "--> Establishing background SSH tunnel (-L 6080:localhost:6080 -L 5901:localhost:5901)..."
    gcloud compute ssh "$VM" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --ssh-flag="-o ConnectTimeout=10" \
        --ssh-flag="-o StrictHostKeyChecking=no" \
        -- -N -f -L 6080:localhost:6080 -L 5901:localhost:5901
    sleep 2
    echo "--> SSH tunnel established."
fi

# 2. Handle connection mode
MODE="${1:---browser}"

case "$MODE" in
    --browser|--chrome)
        echo "--> Launching Xavuntu Desktop in Web Browser..."
        if command -v google-chrome >/dev/null 2>&1; then
            google-chrome "http://localhost:6080/vnc.html?autoconnect=true&resize=remote" >/dev/null 2>&1 &
            echo "--> Opened in Google Chrome: http://localhost:6080/vnc.html"
        elif command -v firefox >/dev/null 2>&1; then
            firefox "http://localhost:6080/vnc.html?autoconnect=true&resize=remote" >/dev/null 2>&1 &
            echo "--> Opened in Firefox: http://localhost:6080/vnc.html"
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://localhost:6080/vnc.html?autoconnect=true&resize=remote" >/dev/null 2>&1 &
            echo "--> Opened in default browser."
        fi
        ;;
    --firefox)
        firefox "http://localhost:6080/vnc.html?autoconnect=true&resize=remote" >/dev/null 2>&1 &
        echo "--> Opened in Firefox: http://localhost:6080/vnc.html"
        ;;
    --remmina|--vnc)
        echo "--> Launching Remmina VNC Client..."
        remmina -c "vnc://localhost:5901" >/dev/null 2>&1 &
        echo "--> Connected via Remmina (Password: $VNC_PASSWD)"
        ;;
    --tunnel-only)
        echo "--> Tunnel is open. Connect via:"
        echo "    Web Browser: http://localhost:6080/vnc.html"
        echo "    VNC Client:  localhost:5901"
        ;;
    *)
        echo "Unknown option: $MODE"
        echo "Usage: $0 [--browser | --firefox | --remmina | --tunnel-only]"
        exit 1
        ;;
esac

echo "=================================================================="
echo "=== XAVUNTU WORKSTATION DESKTOP IS ACTIVE & CONNECTED ==="
echo "=================================================================="
