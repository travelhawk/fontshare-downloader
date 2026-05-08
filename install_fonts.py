#!/usr/bin/env python3
"""
Fontshare font installer.

Installs extracted font files from the downloader output on Windows, macOS, and Linux.
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


INSTALLABLE_EXTENSIONS = {".otf", ".ttf", ".ttc", ".otc"}


class FontInstaller:
    """Install extracted Fontshare fonts for the current platform."""

    def __init__(
        self,
        fonts_dir: str = "./downloads/fonts",
        scope: str = "user",
        verbose: bool = False,
    ):
        self.fonts_dir = Path(fonts_dir)
        self.scope = scope
        self.verbose = verbose
        self.os_type = platform.system().lower()

        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            force=True,
        )
        self.logger = logging.getLogger(__name__)
        self.target_dir = self._get_target_directory()

    def _get_target_directory(self) -> Path:
        """Return the install directory for the selected OS and scope."""
        if self.os_type == "windows":
            if self.scope == "system":
                return Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
            return Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"

        if self.os_type == "darwin":
            if self.scope == "system":
                return Path("/Library/Fonts")
            return Path.home() / "Library" / "Fonts"

        if self.scope == "system":
            return Path("/usr/local/share/fonts")

        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / "fonts"
        return Path.home() / ".local" / "share" / "fonts"

    def _ensure_target_directory(self):
        """Create the target directory when possible before installation."""
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def _windows_is_admin(self) -> bool:
        """Return True when the process is elevated on Windows."""
        if self.os_type != "windows":
            return False

        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _windows_value_name(self, font_path: Path) -> str:
        """Build a registry label for a Windows font file."""
        kind = "OpenType" if font_path.suffix.lower() in {".otf", ".otc"} else "TrueType"
        return f"{font_path.stem} ({kind})"

    def _register_windows_font(self, font_path: Path):
        """Register an installed Windows font for the selected scope."""
        import ctypes
        import winreg

        key_root = winreg.HKEY_LOCAL_MACHINE if self.scope == "system" else winreg.HKEY_CURRENT_USER
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        value_name = self._windows_value_name(font_path)
        value_data = font_path.name if self.scope == "system" else str(font_path)

        with winreg.OpenKey(key_root, key_path, 0, winreg.KEY_SET_VALUE) as registry_key:
            winreg.SetValueEx(registry_key, value_name, 0, winreg.REG_SZ, value_data)

        gdi32 = ctypes.windll.gdi32
        added = gdi32.AddFontResourceExW(str(font_path), 0, 0)
        if added == 0:
            self.logger.debug("Windows font resource refresh returned 0 for %s", font_path.name)

    def _refresh_windows_fonts(self):
        """Broadcast the Windows font change notification."""
        try:
            import ctypes

            hwnd_broadcast = 0xFFFF
            wm_fontchange = 0x001D
            smto_abortifhung = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                hwnd_broadcast,
                wm_fontchange,
                0,
                0,
                smto_abortifhung,
                1000,
                None,
            )
        except Exception as exc:
            self.logger.debug("Windows font notification failed: %s", exc)

    def _refresh_linux_font_cache(self):
        """Refresh the fontconfig cache on Linux when available."""
        fc_cache = shutil.which("fc-cache")
        if not fc_cache:
            self.logger.warning("fc-cache not found; new fonts may not appear until the cache refreshes.")
            return

        try:
            subprocess.run(
                [fc_cache, "-f", str(self.target_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            self.logger.warning("fc-cache failed: %s", detail)

    def find_font_files(self) -> List[Path]:
        """Return installable font files from the extracted downloads directory."""
        if not self.fonts_dir.exists():
            return []

        font_files: List[Path] = []
        for path in self.fonts_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in INSTALLABLE_EXTENSIONS:
                continue
            if any(part.lower() == "web" for part in path.parts):
                continue
            font_files.append(path)

        return sorted(font_files)

    def install_font(self, source_path: Path) -> str:
        """Install a single font file and return installed, skipped, or failed."""
        destination = self.target_dir / source_path.name
        try:
            self._ensure_target_directory()
            if destination.exists() and destination.stat().st_size == source_path.stat().st_size:
                self.logger.info("Skipping %s (already installed)", source_path.name)
                return "skipped"

            shutil.copy2(source_path, destination)
            if self.os_type == "windows":
                self._register_windows_font(destination)

            self.logger.info("Installed %s", source_path.name)
            return "installed"
        except Exception as exc:
            self.logger.error("Failed to install %s: %s", source_path.name, exc)
            return "failed"

    def install_all_fonts(self) -> Dict[str, int]:
        """Install all extracted fonts for the selected platform and scope."""
        if self.os_type == "windows" and self.scope == "system" and not self._windows_is_admin():
            raise PermissionError("system-wide Windows installs require administrator privileges")

        font_files = self.find_font_files()
        stats = {"processed": len(font_files), "installed": 0, "skipped": 0, "failed": 0}

        if not font_files:
            self.logger.warning("No extracted font files found in %s", self.fonts_dir)
            return stats

        self.logger.info("Found %s installable font files", len(font_files))
        self.logger.info("Installing fonts to %s", self.target_dir)

        for font_path in font_files:
            result = self.install_font(font_path)
            stats[result] += 1

        if self.os_type == "windows":
            self._refresh_windows_fonts()
        elif self.os_type == "linux":
            self._refresh_linux_font_cache()

        return stats

    def run(self):
        """Run the installer CLI flow."""
        print("Fontshare Font Installer")
        print("=" * 40)
        print(f"Operating System: {platform.system()}")
        print(f"Install Scope: {self.scope}")
        print(f"Source Directory: {self.fonts_dir}")
        print(f"Target Directory: {self.target_dir}")
        print()

        if self.os_type == "windows" and self.scope == "system" and not self._windows_is_admin():
            print("System-wide Windows installs require an elevated shell.")
            print("Use `--scope user` to install without administrator privileges.")
            return 1

        try:
            stats = self.install_all_fonts()
        except PermissionError as exc:
            print(f"Error: {exc}")
            return 1
        except Exception as exc:
            print(f"Error: {exc}")
            self.logger.exception("Unexpected error occurred")
            return 1

        print()
        print("=" * 50)
        print("Font Installation Complete")
        print("=" * 50)
        print(f"Font files processed: {stats['processed']}")
        print(f"Installed: {stats['installed']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Failed: {stats['failed']}")
        print(f"Fonts installed to: {self.target_dir}")

        if self.os_type == "linux":
            print("Fontconfig cache refresh was attempted automatically.")
        elif self.os_type in {"windows", "darwin"}:
            print("Restart any open design apps if the new fonts do not appear immediately.")

        return 0


def _configure_console_encoding():
    """Prefer UTF-8 console output when available."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except ValueError:
                pass


def main():
    """Command line interface."""
    _configure_console_encoding()

    parser = argparse.ArgumentParser(description="Install extracted Fontshare fonts")
    parser.add_argument(
        "--fonts-dir",
        default="./downloads/fonts",
        help="Directory containing extracted font families",
    )
    parser.add_argument(
        "--scope",
        choices=("user", "system"),
        default="user",
        help="Install fonts for the current user or system-wide",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    installer = FontInstaller(args.fonts_dir, scope=args.scope, verbose=args.verbose)
    raise SystemExit(installer.run())


if __name__ == "__main__":
    main()
