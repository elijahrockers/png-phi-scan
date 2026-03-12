"""Tests for PNG PHI scan models."""

import json

from png_phi_scan.models import (
    BoundingBox,
    FileError,
    PixelPHIFinding,
    ScanReport,
    Severity,
)


def test_severity_values():
    assert Severity.HIGH == "high"
    assert Severity.LOW == "low"


def test_bounding_box_serialization():
    bbox = BoundingBox(x=10, y=20, width=100, height=50)
    data = json.loads(bbox.model_dump_json())
    assert data == {"x": 10, "y": 20, "width": 100, "height": 50}
    assert BoundingBox.model_validate(data) == bbox


def test_pixel_finding_round_trip():
    finding = PixelPHIFinding(
        text="SMITH, JOHN",
        bbox=BoundingBox(x=5, y=10, width=120, height=20),
        confidence=0.95,
        severity=Severity.HIGH,
        frame_index=0,
    )
    data = json.loads(finding.model_dump_json())
    restored = PixelPHIFinding.model_validate(data)
    assert restored.text == "SMITH, JOHN"
    assert restored.frame_index == 0
    assert restored.confidence == 0.95


def test_scan_report_has_phi_true():
    report = ScanReport(
        filepath="test.png",
        image_width=400,
        image_height=300,
        n_frames=1,
        pixel_findings=[
            PixelPHIFinding(
                text="MRN: 123",
                bbox=BoundingBox(x=0, y=0, width=50, height=10),
                confidence=0.9,
                severity=Severity.HIGH,
                frame_index=0,
            )
        ],
        total_phi_count=1,
        risk_level=Severity.HIGH,
        recommendations=["Redact burned-in PHI text from image before sharing"],
    )
    assert report.has_phi is True


def test_scan_report_has_phi_false():
    report = ScanReport(
        filepath="clean.png",
        image_width=256,
        image_height=256,
        n_frames=1,
        pixel_findings=[],
        total_phi_count=0,
        risk_level=Severity.LOW,
        recommendations=["No PHI detected — file appears safe for sharing"],
    )
    assert report.has_phi is False


def test_scan_report_round_trip():
    report = ScanReport(
        filepath="test.gif",
        image_width=400,
        image_height=300,
        n_frames=3,
        pixel_findings=[
            PixelPHIFinding(
                text="DOE, JANE",
                bbox=BoundingBox(x=10, y=10, width=100, height=20),
                confidence=0.88,
                severity=Severity.HIGH,
                frame_index=1,
            )
        ],
        total_phi_count=1,
        risk_level=Severity.HIGH,
        recommendations=["Redact burned-in PHI text from image before sharing"],
    )
    data = json.loads(report.model_dump_json())
    restored = ScanReport.model_validate(data)
    assert restored.filepath == "test.gif"
    assert restored.n_frames == 3
    assert len(restored.pixel_findings) == 1
    assert restored.pixel_findings[0].frame_index == 1


def test_file_error_serialization():
    error = FileError(filepath="bad.png", error="corrupt file")
    data = json.loads(error.model_dump_json())
    assert data["filepath"] == "bad.png"
    assert data["error"] == "corrupt file"
