# Fontshare Downloader

Python scripts for downloading the current [Fontshare](https://www.fontshare.com/) catalog, extracting each family, and optionally installing the resulting desktop fonts.

![Fontshare downloader demo](docs/demo/fontshare-downloader-demo.gif)

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

Current Python dependencies: \
`aiohttp`, `beautifulsoup4`, `click`, `requests`, `tqdm`

## Usage

### Download the catalog

Use this to download and install the fonts automatically:

```bash
python fontshare_downloader.py --install
```

Use this to only download the fonts:

```bash
python fontshare_downloader.py
```

What the main downloader does:

- fetches the live Fontshare catalog from `https://api.fontshare.com/v2/fonts`
- falls back to `font_list.py` if live discovery fails
- downloads each family archive
- extracts each family immediately into `downloads/fonts/<slug>/`
- records logs and metadata under `downloads/logs/` and `downloads/metadata/`

### Advanced usage

**Useful options:**

```bash
python fontshare_downloader.py --output-dir ./downloads
python fontshare_downloader.py --rate-limit 1.0
python fontshare_downloader.py --max-concurrent 3
python fontshare_downloader.py --install --install-scope system
python fontshare_downloader.py --verbose
```

---

**Install-only (without re-downloading):**

```bash
# Current user scope
python install_fonts.py --scope user

# System-wide scope
python install_fonts.py --scope system

# Custom directory
python install_fonts.py --fonts-dir ./downloads/fonts --scope user
```

## Repository Layout

```text
.
├── README.md
├── requirements.txt
├── fontshare_downloader.py      # Supported downloader CLI
├── install_fonts.py             # Supported installer CLI
├── font_list.py                 # Fallback font slug lists
├── run_downloader.bat           # Windows wrapper for the main downloader
├── docs/
    ├── demo/
    │   ├── fontshare-downloader-demo.gif
    │   └── fontshare-downloader-demo.mp4
    └── prd.md
```

## Default Output Layout

Runtime output is written to downloads/ by default. The installer ignores web-only assets and focuses on `.otf`, `.ttf`, `.ttc`, and `.otc`.

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

## Notes

**Licensing**: Font downloads and use remain subject to Fontshare's licensing terms.

**Etiquette**: Use conservative rate limits and concurrency to remain respectful to Fontshare's service.

**Permissions**: If system-wide installation fails on Windows, run the shell as Administrator or use --scope user.

## Contributors

- [exadizon](https://github.com/exadizon)
- [travelhawk](https://github.com/travelhawk)
