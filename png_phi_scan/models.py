"""Pydantic models for PNG/GIF PHI detection results."""

from enum import Enum

from pydantic import BaseModel


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BoundingBox(BaseModel):
    """Pixel coordinates for detected text region."""

    x: int
    y: int
    width: int
    height: int


class PixelPHIFinding(BaseModel):
    """A PHI finding from burned-in pixel text detected via OCR."""

    text: str
    bbox: BoundingBox
    confidence: float
    severity: Severity
    frame_index: int  # 0 for PNG, 0..N for GIF frames


class ScanReport(BaseModel):
    """Complete PHI scan report for a PNG or GIF file."""

    filepath: str
    image_width: int
    image_height: int
    n_frames: int
    pixel_findings: list[PixelPHIFinding]
    total_phi_count: int
    risk_level: Severity
    recommendations: list[str]

    @property
    def has_phi(self) -> bool:
        return self.total_phi_count > 0


class FileError(BaseModel):
    """A per-file error encountered during batch scanning."""

    filepath: str
    error: str
