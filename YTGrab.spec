# PyInstaller build recipe. Run on each OS:  pyinstaller YTGrab.spec
import sys
import deno
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

deno_exe = deno.find_deno_bin()  # the Deno binary installed by `pip install deno`

datas = []
datas += [("ui", "ui")]
datas += collect_data_files("webview")
datas += collect_data_files("yt_dlp_ejs")
datas += collect_data_files("imageio_ffmpeg", include_py_files=False)

binaries = [(deno_exe, "deno_bin")]

hiddenimports = collect_submodules("yt_dlp") + collect_submodules("yt_dlp_ejs") + ["webview"]

a = Analysis(
    ["app.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "numpy", "PIL.ImageQt"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="YTGrab",
              console=False, upx=False, icon="icon/YTGrab.icns")
    coll = COLLECT(exe, a.binaries, a.datas, name="YTGrab", upx=False)
    app = BUNDLE(coll, name="YTGrab.app", bundle_identifier="com.ytgrab.app",
                 icon="icon/YTGrab.icns",
                 info_plist={
                     "NSHighResolutionCapable": True,
                     # lets the Chrome extension open the app with ytgrab:// links
                     "CFBundleURLTypes": [{"CFBundleURLName": "com.ytgrab.app",
                                           "CFBundleURLSchemes": ["ytgrab"]}],
                 })
else:
    # Windows: one single YTGrab.exe
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="YTGrab",
              console=False, upx=False, icon="icon/YTGrab.ico")
