# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Glow Deploy GUI.

Built by .github/workflows/gui-release.yml, which — before invoking
`pyinstaller pyinstaller.spec` — runs `tsc` to produce static/js/*.js,
downloads the pinned terraform/packer binaries into `bin/` next to this
file, and writes the release tag into `VERSION`. All three are picked up
here via datas/binaries; see paths.py/binaries.py/version.py for how the
frozen app finds them again at runtime.
"""

from pathlib import Path

# SPECPATH is injected into the spec's exec() namespace by PyInstaller itself
# (this file has no real __file__ / module identity when run as a spec).
GUI_DIR = Path(SPECPATH).resolve()  # noqa: F821
BIN_DIR = GUI_DIR / "bin"

binaries = [(str(path), "bin") for path in BIN_DIR.iterdir()] if BIN_DIR.exists() else []

datas = [
    (str(GUI_DIR / "templates"), "glow_deploy/gui/templates"),
    (str(GUI_DIR / "static"), "glow_deploy/gui/static"),
]
version_file = GUI_DIR / "VERSION"
if version_file.exists():
    datas.append((str(version_file), "glow_deploy/gui"))

a = Analysis(
    [str(GUI_DIR / "main.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="glow-deploy",
    console=False,
)
