# Fontshare Downloader

Python scripts for downloading the current Fontshare catalog, extracting each family, and optionally installing the resulting desktop fonts.

The repository now has one primary workflow and a small set of archived experiments. If you only want the supported path, use `fontshare_downloader.py` for downloading and `install_fonts.py` for installation.

## Current Status

- `fontshare_downloader.py` is the main downloader.
- `install_fonts.py` is the main cross-platform installer for extracted desktop fonts.
- `run_downloader.bat` is a Windows convenience wrapper for the main downloader.
- `install_fonts_quick.bat` and `install_system_fonts.bat` are Windows-only legacy helpers kept for fallback use.
- `scripts/legacy/` contains older prototypes, debug scripts, and superseded one-off utilities.
- `docs/prd.md` is the original planning document, kept as project history rather than current behavior.

## Repository Layout

```text
.
├── README.md
├── requirements.txt
├── fontshare_downloader.py      # Supported downloader CLI
├── install_fonts.py             # Supported installer CLI
├── font_list.py                 # Fallback font slug lists
├── run_downloader.bat           # Windows wrapper for the main downloader
├── install_fonts_quick.bat      # Legacy Windows fallback wrapper
├── install_system_fonts.bat     # Legacy Windows admin wrapper
├── docs/
│   └── prd.md
```

Runtime output is written to `downloads/` by default and should be treated as generated data, not source code.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

Current Python dependencies:

- `aiohttp`
- `beautifulsoup4`
- `click`
- `requests`
- `tqdm`

## Supported Usage

### Download the catalog

Use this to download the fonts automatically:

```bash
python fontshare_downloader.py
```

Use this to download and install the fonts automatically:

```
python fontshare_downloader.py --install
```

Useful options:

```bash
python fontshare_downloader.py --output-dir ./downloads
python fontshare_downloader.py --rate-limit 1.0
python fontshare_downloader.py --max-concurrent 3
python fontshare_downloader.py --install --install-scope system
python fontshare_downloader.py --verbose
```

What the main downloader does:

- fetches the live Fontshare catalog from `https://api.fontshare.com/v2/fonts`
- falls back to `font_list.py` if live discovery fails
- downloads each family archive
- extracts each family immediately into `downloads/fonts/<slug>/`
- records logs and metadata under `downloads/logs/` and `downloads/metadata/`

### Install extracted fonts

Install for the current user:

```bash
python install_fonts.py --scope user
```

Install system-wide:

```bash
python install_fonts.py --scope system
```

You can also point the installer at a custom extraction directory:

```bash
python install_fonts.py --fonts-dir ./downloads/fonts --scope user
```

## Default Output Layout

```text
downloads/
├── fonts/
│   └── <font-slug>/
│       ├── OTF/
│       ├── TTF/
│       └── WEB/
├── logs/
│   └── download.log
└── metadata/
    └── font-list.json
```

The installer ignores web-only assets and installs desktop font files such as `.otf`, `.ttf`, `.ttc`, and `.otc`.

## Notes

- Font downloads and use remain subject to Fontshare's licensing terms.
- Use conservative rate limits and concurrency so the downloader remains respectful to Fontshare's service.
- If system-wide installation fails on Windows, run the shell with administrator privileges or use `--scope user`.

## Contributors

- [exadizon](https://github.com/exadizon)
- [travelhawk](https://github.com/travelhawk)
