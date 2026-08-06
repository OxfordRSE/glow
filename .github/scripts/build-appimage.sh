#!/usr/bin/env bash
# Wraps a PyInstaller onefile binary into an AppImage. Exits non-zero on any
# failure so the caller can fall back to a plain tarball (see gui-release.yml)
# — AppImage packaging (appimagetool availability, FUSE) is the part of this
# pipeline most likely to be fiddly on a given CI runner.
set -euo pipefail

BINARY_PATH="$1"  # path to the PyInstaller onefile executable
OUTPUT_NAME="$2"  # output name, without extension

WORK_DIR="$(mktemp -d)"
APPDIR="${WORK_DIR}/AppDir"
mkdir -p "${APPDIR}/usr/bin"
cp "${BINARY_PATH}" "${APPDIR}/usr/bin/glow-deploy"
chmod +x "${APPDIR}/usr/bin/glow-deploy"

cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/glow-deploy" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

cat > "${APPDIR}/glow-deploy.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Glow Deploy
Exec=glow-deploy
Icon=glow-deploy
Categories=Utility;
EOF

# appimagetool requires an icon file to exist; a placeholder is fine — this
# isn't the app's branding, just satisfying the packaging tool.
base64 -d > "${APPDIR}/glow-deploy.png" <<'EOF'
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=
EOF

APPIMAGETOOL="${WORK_DIR}/appimagetool"
curl -fsSL "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" -o "${APPIMAGETOOL}"
chmod +x "${APPIMAGETOOL}"

ARCH=x86_64 "${APPIMAGETOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_NAME}.AppImage"
