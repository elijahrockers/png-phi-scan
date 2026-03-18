"""Lazy singleton EasyOCR reader with GPU auto-detection.

Avoids reloading the ~100MB model per call. Mirrors the pattern from
dicom-phi-scan/src/pixel_scanner.py.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MIN_OCR_CONFIDENCE = 0.30

# Lazy singleton state
_reader: Any = None  # easyocr.Reader, created lazily
_use_gpu: bool | None = None


def init_reader(gpu: bool | None = None) -> None:
    """Initialize the EasyOCR reader singleton.

    Args:
        gpu: True to force GPU, False to force CPU, None to auto-detect via CUDA.
    """
    import easyocr  # deferred — heavy (loads torch)

    global _reader, _use_gpu
    if gpu is None:
        import torch

        _use_gpu = torch.cuda.is_available()
    else:
        _use_gpu = gpu
    logger.info("EasyOCR using %s", "GPU (CUDA)" if _use_gpu else "CPU")
    _reader = easyocr.Reader(["en"], gpu=_use_gpu)


def get_reader() -> Any:
    """Return the shared EasyOCR Reader, creating it on first use."""
    global _reader
    if _reader is None:
        init_reader()
    return _reader
