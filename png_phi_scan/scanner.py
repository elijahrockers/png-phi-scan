"""PNG/GIF PHI scanning pipeline.

Pixel-only scan: runs OCR on image frames to detect burned-in text.
For GIF files, iterates over animation frames up to a configurable cap.
"""

import logging
import time

from PIL import Image, ImageSequence

from .models import Severity, ScanReport
from .pixel_scanner import scan_image

logger = logging.getLogger(__name__)


def scan_file(filepath: str, max_frames: int = 50, batch_size: int = 16) -> ScanReport:
    """Scan a PNG or GIF file for PHI in pixel data.

    Args:
        filepath: Path to .png or .gif file.
        max_frames: Maximum number of GIF frames to scan.
        batch_size: EasyOCR recognition batch size (higher = faster on GPU).

    Returns:
        ScanReport with all findings and recommendations.
    """
    t_start = time.monotonic()
    logger.debug("scan_file: start %s", filepath)

    img = Image.open(filepath)
    width, height = img.size
    n_frames = getattr(img, "n_frames", 1)

    pixel_findings = []

    if n_frames == 1:
        pixel_findings.extend(scan_image(img, 0, batch_size=batch_size))
    else:
        frames_to_scan = min(n_frames, max_frames)
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            if i >= frames_to_scan:
                break
            pixel_findings.extend(scan_image(frame, i, batch_size=batch_size))

    img.close()
    logger.debug("scan_file: done %s in %.2fs", filepath, time.monotonic() - t_start)

    total = len(pixel_findings)

    recommendations = []
    if pixel_findings:
        recommendations.append(
            "Redact burned-in PHI text from image before sharing"
        )
    else:
        recommendations.append("No PHI detected — file appears safe for sharing")

    risk_level = Severity.HIGH if total > 0 else Severity.LOW

    return ScanReport(
        filepath=filepath,
        image_width=width,
        image_height=height,
        n_frames=n_frames,
        pixel_findings=pixel_findings,
        total_phi_count=total,
        risk_level=risk_level,
        recommendations=recommendations,
    )
