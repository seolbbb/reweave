"""PyInstaller build definition for the Windows desktop application."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


project_root = Path(SPECPATH).parent
source_root = project_root / "src"
frontend_dist = source_root / "reweave" / "web" / "dist"

datas = [(str(frontend_dist), "reweave/web/dist")]
binaries = []
hiddenimports = []

for package in ("fastembed", "onnxruntime"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += collect_submodules("keyring.backends")
hiddenimports += collect_submodules("webview")

desktop_analysis = Analysis(
    [str(project_root / "packaging" / "reweave_desktop.py")],
    pathex=[str(source_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)

native_host_analysis = Analysis(
    [str(project_root / "packaging" / "reweave_native_host.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)

MERGE(
    (desktop_analysis, "reweave_desktop", "Reweave"),
    (native_host_analysis, "reweave_native_host", "ReweaveNativeHost"),
)

desktop_python_archive = PYZ(desktop_analysis.pure)
native_host_python_archive = PYZ(native_host_analysis.pure)

desktop_executable = EXE(
    desktop_python_archive,
    desktop_analysis.dependencies,
    desktop_analysis.scripts,
    [],
    exclude_binaries=True,
    name="Reweave",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

native_host_executable = EXE(
    native_host_python_archive,
    native_host_analysis.dependencies,
    native_host_analysis.scripts,
    [],
    exclude_binaries=True,
    name="ReweaveNativeHost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    desktop_executable,
    native_host_executable,
    desktop_analysis.binaries,
    desktop_analysis.datas,
    native_host_analysis.binaries,
    native_host_analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Reweave",
)
