#!/usr/bin/env bash
# install.sh
set -e

INSTALL_DIR="$HOME/.local/share/timesheet"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "Installing Timesheet..."
mkdir -p "$INSTALL_DIR"
cp *.py "$INSTALL_DIR/"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/timesheet" << EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec python3 "$INSTALL_DIR/timesheet.py" "\$@"
EOF
chmod +x "$BIN_DIR/timesheet"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/timesheet.desktop" << EOF
[Desktop Entry]
Name=Timesheet
Comment=Time tracking
Exec=$BIN_DIR/timesheet
Icon=office-calendar
Terminal=false
Type=Application
Categories=Office;Utility;
Keywords=time;tracking;hours;timesheet;
StartupWMClass=timesheet
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo ""
echo "Done. Run: timesheet"
echo ""
echo "Hyprland float rule:"
echo "  windowrulev2 = float, class:timesheet"
echo "  windowrulev2 = size 860 640, class:timesheet"
echo "  windowrulev2 = center, class:timesheet"
