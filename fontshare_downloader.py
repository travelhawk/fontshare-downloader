"""
Fontshare bulk font downloader.

Discovers downloadable font families from the live Fontshare API and downloads
each family ZIP to a local output directory.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional
from urllib.parse import quote

import aiohttp
import click
from tqdm.asyncio import tqdm


class FontshareDownloader:
    """Discover and download font families from Fontshare."""

    EXTRACTED_FONT_EXTENSIONS = {
        ".otf",
        ".ttf",
        ".ttc",
        ".otc",
        ".woff",
        ".woff2",
        ".eot",
    }

    def __init__(
        self,
        output_dir: str = "./downloads",
        rate_limit: float = 1.0,
        max_concurrent: int = 3,
        install_after_download: bool = False,
        install_scope: str = "user",
        verbose: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.rate_limit = rate_limit
        self.max_concurrent = max_concurrent
        self.install_after_download = install_after_download
        self.install_scope = install_scope
        self.verbose = verbose
        self.max_retries = 3
        self.base_url = "https://api.fontshare.com/v2"
        self.user_agent = (
            "fontshare-downloader/2.0 "
            "(https://github.com/falk/fontshare-downloader)"
        )

        self.fonts_dir = self.output_dir / "fonts"
        self.logs_dir = self.output_dir / "logs"
        self.metadata_dir = self.output_dir / "metadata"

        self._setup_directories()
        self._setup_logging()

    def _setup_directories(self):
        """Create necessary directories."""
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def _setup_logging(self):
        """Setup logging configuration."""
        log_file = self.logs_dir / "download.log"
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
            force=True,
        )
        self.logger = logging.getLogger(__name__)

    async def discover_fonts(
        self, session: aiohttp.ClientSession
    ) -> List[Dict[str, str]]:
        """Discover all downloadable font families from the live Fontshare API."""
        self.logger.info("Discovering fonts from Fontshare...")

        fonts = await self._fetch_live_font_catalog(session)
        if fonts:
            self.logger.info("Found %s downloadable font families via live API", len(fonts))
            return fonts

        self.logger.warning("Falling back to the bundled font list")
        return self._get_fallback_fonts()

    async def _fetch_live_font_catalog(
        self, session: aiohttp.ClientSession
    ) -> Optional[List[Dict[str, str]]]:
        """Fetch the live font catalog from the Fontshare API."""
        fonts: List[Dict[str, str]] = []
        seen_slugs = set()
        offset = 0
        page_size = 100

        while True:
            try:
                async with session.get(
                    f"{self.base_url}/fonts",
                    params={"offset": offset, "limit": page_size},
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        self.logger.debug(
                            "Catalog request failed: HTTP %s - %s",
                            response.status,
                            body[:200].replace("\n", " "),
                        )
                        return None

                    data = await response.json()
            except Exception as exc:
                self.logger.debug("Live catalog request failed: %s", exc)
                return None

            page_fonts = data.get("fonts") or []
            if not page_fonts:
                break

            for font in page_fonts:
                slug = font.get("slug")
                name = font.get("name")
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                fonts.append({"slug": slug, "name": name or slug})

            if not data.get("has_more"):
                break
            offset += len(page_fonts)

        fonts.sort(key=lambda font: font["slug"].lower())
        return fonts or None

    def _get_fallback_fonts(self) -> List[Dict[str, str]]:
        """Return a bundled fallback list if live discovery is unavailable."""
        try:
            from font_list import FONTSHARE_FONTS, POTENTIAL_FONTS

            fallback = []
            seen = set()
            for slug in list(FONTSHARE_FONTS) + list(POTENTIAL_FONTS):
                if slug not in seen:
                    seen.add(slug)
                    fallback.append({"slug": slug, "name": slug})
            return fallback
        except ImportError:
            basic_fonts = [
                "satoshi",
                "cabinet-grotesk",
                "clash-display",
                "general-sans",
                "switzer",
                "clash-grotesk",
                "supreme",
                "author",
                "zodiak",
                "chillax",
            ]
            return [{"slug": slug, "name": slug} for slug in basic_fonts]

    def _font_family_is_ready(self, font_dir: Path) -> bool:
        """Return True when a font family directory already contains extracted files."""
        if not font_dir.exists():
            return False

        for file_path in font_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.EXTRACTED_FONT_EXTENSIONS:
                return True
        return False

    def _archive_members(
        self, zip_ref: zipfile.ZipFile
    ) -> List[tuple[zipfile.ZipInfo, List[str]]]:
        """Return normalized archive members while guarding against path traversal."""
        members: List[tuple[zipfile.ZipInfo, List[str]]] = []
        for file_info in zip_ref.infolist():
            if file_info.is_dir():
                continue

            raw_parts = [
                part
                for part in PurePosixPath(file_info.filename).parts
                if part not in ("", ".")
            ]
            if not raw_parts or any(part == ".." for part in raw_parts):
                continue

            members.append((file_info, raw_parts))

        return members

    def _extract_font_archive(self, zip_path: Path, font_dir: Path):
        """Extract a downloaded Fontshare archive into the family directory."""
        temp_extract_dir = font_dir.parent / f".{font_dir.name}.extracting"
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        extracted_files = 0

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                members = self._archive_members(zip_ref)
                if not members:
                    raise ValueError("archive did not contain any files")

                first_segment = members[0][1][0]
                strip_common_root = all(
                    len(parts) > 1 and parts[0] == first_segment for _, parts in members
                )

                for file_info, parts in members:
                    relative_parts = parts[1:] if strip_common_root else parts
                    if len(relative_parts) > 1 and relative_parts[0].lower() == "fonts":
                        relative_parts = relative_parts[1:]
                    if not relative_parts:
                        continue

                    destination = temp_extract_dir.joinpath(*relative_parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(file_info) as source, open(destination, "wb") as target:
                        shutil.copyfileobj(source, target)
                    extracted_files += 1

            if extracted_files == 0:
                raise ValueError("archive did not contain extractable files")

            if font_dir.exists():
                shutil.rmtree(font_dir)
            os.replace(temp_extract_dir, font_dir)
        except Exception:
            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
            raise

    async def download_font(
        self,
        session: aiohttp.ClientSession,
        font: Dict[str, str],
        semaphore: asyncio.Semaphore,
    ) -> bool:
        """Download a single font family ZIP."""
        slug = font["slug"]
        display_name = font.get("name") or slug
        download_url = f"{self.base_url}/fonts/download/{quote(slug, safe='-')}"
        font_dir = self.fonts_dir / slug
        font_dir.mkdir(parents=True, exist_ok=True)
        legacy_zip = font_dir / f"{slug}.zip"
        temp_file = font_dir / f"{slug}.zip.part"

        if self._font_family_is_ready(font_dir):
            self.logger.info("Skipping %s (already downloaded)", slug)
            return True

        if legacy_zip.exists() and legacy_zip.stat().st_size > 0:
            try:
                self._extract_font_archive(legacy_zip, font_dir)
                legacy_zip.unlink(missing_ok=True)
                self.logger.info("Migrated %s from legacy ZIP layout", display_name)
                return True
            except Exception as exc:
                self.logger.warning("Failed to migrate %s from existing ZIP: %s", slug, exc)

        async with semaphore:
            for attempt in range(1, self.max_retries + 1):
                try:
                    async with session.get(download_url) as response:
                        if response.status == 200:
                            with open(temp_file, "wb") as output:
                                async for chunk in response.content.iter_chunked(64 * 1024):
                                    output.write(chunk)

                            if temp_file.stat().st_size == 0:
                                raise ValueError("received an empty ZIP file")

                            archive_size = temp_file.stat().st_size
                            self._extract_font_archive(temp_file, font_dir)
                            self.logger.info(
                                "Downloaded and extracted %s (%s bytes)",
                                display_name,
                                archive_size,
                            )

                            if self.rate_limit > 0:
                                await asyncio.sleep(self.rate_limit)
                            return True

                        error_body = await response.text()
                        if response.status >= 500 and attempt < self.max_retries:
                            await self._retry_wait(slug, attempt, response.status)
                            continue

                        self.logger.error(
                            "Failed to download %s: HTTP %s - %s",
                            slug,
                            response.status,
                            error_body[:200].replace("\n", " "),
                        )
                        return False

                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                    if attempt < self.max_retries:
                        self.logger.warning(
                            "Retrying %s after attempt %s failed: %s",
                            slug,
                            attempt,
                            exc,
                        )
                        await self._retry_wait(slug, attempt)
                        continue

                    self.logger.error("Error downloading %s: %s", slug, exc)
                    return False
                finally:
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except OSError:
                            pass

        return False

    async def _retry_wait(self, slug: str, attempt: int, status: Optional[int] = None):
        """Back off between retry attempts."""
        delay = min(2 ** (attempt - 1), 8)
        if status is None:
            self.logger.debug("Waiting %.1fs before retrying %s", delay, slug)
        else:
            self.logger.warning(
                "Retrying %s after HTTP %s (attempt %s/%s)",
                slug,
                status,
                attempt,
                self.max_retries,
            )
        await asyncio.sleep(delay)

    async def download_all_fonts(self, fonts: List[Dict[str, str]]) -> Dict[str, int]:
        """Download all discovered fonts with progress tracking."""
        self.logger.info("Starting download of %s fonts...", len(fonts))

        metadata_file = self.metadata_dir / "font-list.json"
        with open(metadata_file, "w", encoding="utf-8") as output:
            json.dump(
                {
                    "fonts": fonts,
                    "total_count": len(fonts),
                    "discovery_time": time.time(),
                    "catalog_endpoint": f"{self.base_url}/fonts",
                },
                output,
                indent=2,
            )

        semaphore = asyncio.Semaphore(self.max_concurrent)
        timeout = aiohttp.ClientTimeout(total=180, connect=30, sock_read=120)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, */*"}
        connector = aiohttp.TCPConnector(limit_per_host=self.max_concurrent)

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
            raise_for_status=False,
        ) as session:
            tasks = [self.download_font(session, font, semaphore) for font in fonts]

            results = []
            for coro in tqdm.as_completed(tasks, desc="Downloading fonts"):
                results.append(await coro)

        success_count = sum(results)
        failed_count = len(results) - success_count
        stats = {
            "total": len(fonts),
            "success": success_count,
            "failed": failed_count,
        }

        self.logger.info(
            "Download complete. Success: %s, Failed: %s",
            success_count,
            failed_count,
        )
        return stats

    async def run(self):
        """Main execution method."""
        start_time = time.time()
        install_stats = None

        discovery_timeout = aiohttp.ClientTimeout(total=60, connect=20, sock_read=30)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, */*"}

        async with aiohttp.ClientSession(
            timeout=discovery_timeout,
            headers=headers,
            raise_for_status=False,
        ) as session:
            fonts = await self.discover_fonts(session)

        if not fonts:
            self.logger.error("No fonts discovered. Please check your internet connection.")
            return

        stats = await self.download_all_fonts(fonts)

        if self.install_after_download and stats["success"] > 0:
            from install_fonts import FontInstaller

            installer = FontInstaller(
                fonts_dir=str(self.fonts_dir),
                scope=self.install_scope,
                verbose=self.verbose,
            )
            install_stats = installer.install_all_fonts()

        duration = time.time() - start_time
        print()
        print("=" * 50)
        print("Fontshare Bulk Download Complete")
        print("=" * 50)
        print(f"Fonts saved to: {self.fonts_dir}")
        print(f"Success: {stats['success']} fonts")
        print(f"Failed: {stats['failed']} fonts")
        print(f"Total time: {duration:.1f} seconds")
        print(f"Logs saved to: {self.logs_dir / 'download.log'}")
        if install_stats is not None:
            print(
                "Installed font files: "
                f"{install_stats['installed']} installed, "
                f"{install_stats['skipped']} skipped, "
                f"{install_stats['failed']} failed"
            )


def _configure_console_encoding():
    """Prefer UTF-8 output so the CLI behaves consistently on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except ValueError:
                pass


@click.command()
@click.option("--output-dir", "-o", default="./downloads", help="Output directory for downloads")
@click.option("--rate-limit", "-r", default=1.0, help="Delay between requests in seconds")
@click.option("--max-concurrent", "-c", default=3, help="Maximum concurrent downloads")
@click.option("--install", is_flag=True, help="Install extracted fonts after download")
@click.option(
    "--install-scope",
    type=click.Choice(["user", "system"], case_sensitive=False),
    default="user",
    show_default=True,
    help="Install target when using --install",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(output_dir, rate_limit, max_concurrent, install, install_scope, verbose):
    """Download all available Fontshare font families."""
    _configure_console_encoding()

    print("Fontshare Bulk Font Downloader")
    print("=" * 40)

    downloader = FontshareDownloader(
        output_dir=output_dir,
        rate_limit=rate_limit,
        max_concurrent=max_concurrent,
        install_after_download=install,
        install_scope=install_scope,
        verbose=verbose,
    )

    try:
        asyncio.run(downloader.run())
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
    except Exception as exc:
        print(f"\nError: {exc}")
        logging.exception("Unexpected error occurred")


if __name__ == "__main__":
    main()
