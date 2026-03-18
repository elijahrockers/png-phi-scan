"""Tests for PNG/GIF PHI scanner.

Requires fixtures to be generated first:
    python fixtures/create_test_fixtures.py
"""

import os

import pytest

from png_phi_scan.scanner import scan_file

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


def _fixture(name: str) -> str:
    path = os.path.join(FIXTURES_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"Fixture not found: {name} (run fixtures/create_test_fixtures.py)")
    return path


def test_clean_png_no_findings():
    report = scan_file(_fixture("test_clean.png"))
    assert report.total_phi_count == 0
    assert report.has_phi is False
    assert report.risk_level.value == "low"
    assert report.n_frames == 1


def test_phi_text_png_has_findings():
    report = scan_file(_fixture("test_phi_text.png"))
    assert report.total_phi_count > 0
    assert report.has_phi is True
    assert report.risk_level.value == "high"
    texts = [f.text for f in report.pixel_findings]
    assert any("SMITH" in t.upper() for t in texts)


def test_clean_gif_no_findings():
    report = scan_file(_fixture("test_clean.gif"))
    assert report.total_phi_count == 0
    assert report.has_phi is False
    assert report.n_frames == 3


def test_phi_text_gif_has_findings():
    report = scan_file(_fixture("test_phi_text.gif"))
    assert report.total_phi_count > 0
    assert report.has_phi is True
    assert report.n_frames == 3
    # PHI should be detected on frame 0
    frame_indices = {f.frame_index for f in report.pixel_findings}
    assert 0 in frame_indices


def test_gif_max_frames_cap():
    """max_frames=1 should only scan the first frame."""
    report = scan_file(_fixture("test_phi_text.gif"), max_frames=1)
    # Should still report total n_frames from the file
    assert report.n_frames == 3
    # All findings should be from frame 0 only
    for f in report.pixel_findings:
        assert f.frame_index == 0


def test_batch_size_passthrough():
    """batch_size parameter threads through to scan_image without error."""
    report = scan_file(_fixture("test_phi_text.png"), batch_size=4)
    assert report.total_phi_count > 0
    assert report.has_phi is True
