# CLAUDE.md — png-phi-scan

## Overview

EasyOCR-based PHI scanner for PNG and GIF images. Pixel-only scanning (no header/tag layer). Sibling project to `dicom-phi-scan` and `nifti-phi-scan`.

## Quick Start

```bash
pip install -e .
python fixtures/create_test_fixtures.py   # Generate synthetic test images
png-phi-scan fixtures/test_phi_text.png              # CLI scan
png-phi-scan --dir path/to/images -o results.jsonl   # Batch scan
pytest                                               # Unit tests
ruff check .                                         # Lint
```

## Architecture

- `png_phi_scan/models.py` — Pydantic models: Severity, BoundingBox, PixelPHIFinding, ScanReport, FileError
- `png_phi_scan/ocr_reader.py` — Lazy singleton EasyOCR reader with GPU auto-detection
- `png_phi_scan/pixel_scanner.py` — `scan_image()` runs OCR on a PIL Image and returns findings
- `png_phi_scan/scanner.py` — `scan_file()` orchestration: opens image, iterates GIF frames, aggregates findings
- `png_phi_scan/cli.py` — argparse CLI with single-file, batch (--dir/--manifest), JSONL streaming, --resume

## Supported Formats

- `.png` — single frame
- `.gif` — animated, scans up to `--max-frames` (default 50)

## Key Differences from nifti-phi-scan

- No header scanning layer (PNG/GIF have no PHI-relevant metadata)
- No slice extraction — works directly with PIL Images
- Frame-based instead of slice-based (GIF animation frames)
- Risk is HIGH if any findings, else LOW (no MEDIUM — no header layer)

## CLI Exit Codes

- 0: all files clean
- 1: PHI detected
- 2: errors occurred

## Conventions

- Python 3.10+, ruff (line-length=100), pytest
- All test/fixture data is synthetic — never use real patient data
