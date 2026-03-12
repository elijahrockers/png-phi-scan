# png-phi-scan

EasyOCR-based PHI scanner for PNG and GIF images. Pixel-only scanning (no header/tag layer). Sibling project to [dicom-phi-scan](https://github.com/elijahrockers/dicom-phi-scan) and [nifti-phi-scan](https://github.com/elijahrockers/nifti-phi-scan).

## Quick Start

```bash
pip install -e .
python fixtures/create_test_fixtures.py   # Generate synthetic test images
png-phi-scan fixtures/test_phi_text.png              # CLI scan
png-phi-scan --dir path/to/images -o results.jsonl   # Batch scan
pytest                                               # Unit tests
```

## How It Works

All detected text in an image is conservatively flagged as potential PHI — burned-in text in medical images is inherently suspicious. The scanner uses [EasyOCR](https://github.com/JaidedAI/EasyOCR) with GPU auto-detection (falls back to CPU).

- **PNG** — single-frame scan
- **GIF** — animated, scans up to `--max-frames` frames (default 50)

Risk is **HIGH** if any text is found, otherwise **LOW**.

## CLI Usage

```
png-phi-scan IMAGE                         # Scan a single file
png-phi-scan --dir ./images -o results.jsonl   # Recursive batch scan
png-phi-scan --manifest files.txt -o out.jsonl # Scan from file list
png-phi-scan --dir ./images -o out.jsonl --resume  # Resume interrupted scan
```

### Options

| Flag | Description |
|------|-------------|
| `--dir DIR` | Recursively scan directory for `.png`/`.gif` files |
| `--manifest FILE` | File containing one image path per line |
| `-o FILE` | Output file (JSON for single, JSONL for batch) |
| `--max-frames N` | Max GIF frames to scan (default: 50) |
| `--cpu` | Force CPU even if GPU is available |
| `--timeout SEC` | Per-file timeout in seconds |
| `--resume` | Skip files already in output JSONL |
| `--limit N` | Max files to scan |
| `--chunk-size N` | Files per chunk (for SLURM array jobs) |
| `--chunk-index N` | Zero-based chunk index |
| `-L` | Follow symbolic links |
| `-v` | Verbose logging |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All files clean |
| 1 | PHI detected |
| 2 | Errors occurred |

### Querying JSONL Output

```bash
jq 'select(.risk_level == "high") | .filepath' results.jsonl
```

## Architecture

| Module | Purpose |
|--------|---------|
| `png_phi_scan/models.py` | Pydantic models: Severity, BoundingBox, PixelPHIFinding, ScanReport, FileError |
| `png_phi_scan/ocr_reader.py` | Lazy singleton EasyOCR reader with GPU auto-detection |
| `png_phi_scan/pixel_scanner.py` | `scan_image()` — runs OCR on a PIL Image, returns findings |
| `png_phi_scan/scanner.py` | `scan_file()` — orchestration, GIF frame iteration |
| `png_phi_scan/cli.py` | argparse CLI with batch, JSONL streaming, resume |

## Development

```bash
pip install -e ".[dev]"
pytest           # Run tests
ruff check .     # Lint
```

All test and fixture data is synthetic — no real patient data is used.
