"""Build OpenShelf.exe, a single file people can double-click (no Python needed).

One-time setup (in this folder):
    py -3 -m pip install pyinstaller pillow
Build:
    py -3 packaging/build_windows.py
Result:
    dist/OpenShelf.exe

Upload dist/OpenShelf.exe to a GitHub Release so people can download it.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ICON = os.path.join(HERE, "openshelf.ico")
SEP = ";" if os.name == "nt" else ":"


def main():
    if not os.path.isfile(ICON):
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_icon.py")])
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "OpenShelf",
        "--icon", ICON,
        "--version-file", os.path.join(HERE, "version_info.txt"),
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", os.path.join(ROOT, "build"),
        # the web interface and the original PaperHarvest engine ship inside the exe
        "--add-data", f"{os.path.join(ROOT, 'web')}{SEP}web",
        "--add-data", f"{os.path.join(ROOT, 'PaperHarvest', 'paperharvest.py')}{SEP}PaperHarvest",
        "--add-data", f"{os.path.join(ROOT, 'PaperHarvest', 'LICENSE')}{SEP}PaperHarvest",
        "--add-data", f"{os.path.join(ROOT, 'LICENSE')}{SEP}.",
        # PaperHarvest is loaded by path at runtime, so list what it imports
        "--hidden-import", "csv",
        "--hidden-import", "http.server",
        "--hidden-import", "webbrowser",
        os.path.join(ROOT, "openshelf.py"),
    ]
    subprocess.check_call(args, cwd=ROOT)
    print("\nBuilt:", os.path.join(ROOT, "dist", "OpenShelf.exe"))


if __name__ == "__main__":
    main()
