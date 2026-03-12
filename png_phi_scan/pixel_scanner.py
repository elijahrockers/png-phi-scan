"""OCR-based pixel PHI detection on PNG/GIF images.

Runs EasyOCR on image frames and flags all detected text as
potential PHI — burned-in text in medical images is inherently suspicious.
"""

import numpy as np
from PIL import Image

from .models import BoundingBox, PixelPHIFinding, Severity
from .ocr_reader import MIN_OCR_CONFIDENCE, get_reader


def scan_image(image: Image.Image, frame_index: int = 0) -> list[PixelPHIFinding]:
    """Run OCR on a single image/frame and return PHI findings.

    Args:
        image: PIL Image to scan.
        frame_index: Frame index (0 for PNG, 0..N for GIF).

    Returns:
        List of PixelPHIFinding for detected text.
    """
    rgb = image.convert("RGB")
    img_array = np.array(rgb)

    reader = get_reader()
    ocr_results = reader.readtext(img_array)

    findings: list[PixelPHIFinding] = []
    for bbox_pts, text, conf in ocr_results:
        text = text.strip()
        if not text or conf < MIN_OCR_CONFIDENCE:
            continue

        # bbox_pts is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [pt[0] for pt in bbox_pts]
        ys = [pt[1] for pt in bbox_pts]
        x = int(min(xs))
        y = int(min(ys))
        width = int(max(xs) - x)
        height = int(max(ys) - y)

        findings.append(
            PixelPHIFinding(
                text=text,
                bbox=BoundingBox(x=x, y=y, width=width, height=height),
                confidence=round(conf, 4),
                severity=Severity.HIGH,
                frame_index=frame_index,
            )
        )

    return findings
