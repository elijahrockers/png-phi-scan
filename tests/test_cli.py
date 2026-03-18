"""Tests for CLI file collection utilities (no OCR needed)."""

import json
import os

import pytest

from png_phi_scan.cli import _collect_files, _is_image_ext, _load_done_paths, _walk_images


@pytest.fixture
def image_tree(tmp_path):
    """Create a directory tree with image and non-image files."""
    # root/a.png, root/b.gif, root/c.txt
    (tmp_path / "a.png").write_bytes(b"fake png")
    (tmp_path / "b.gif").write_bytes(b"fake gif")
    (tmp_path / "c.txt").write_text("not an image")
    # root/sub/d.PNG (uppercase extension)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "d.PNG").write_bytes(b"fake png")
    (sub / "e.jpg").write_bytes(b"fake jpg")
    return tmp_path


class TestIsImageExt:
    def test_png(self):
        assert _is_image_ext("photo.png") is True

    def test_gif(self):
        assert _is_image_ext("anim.gif") is True

    def test_uppercase(self):
        assert _is_image_ext("SCAN.PNG") is True
        assert _is_image_ext("ANIM.GIF") is True

    def test_non_image(self):
        assert _is_image_ext("file.txt") is False
        assert _is_image_ext("image.jpg") is False
        assert _is_image_ext("data.dcm") is False

    def test_no_extension(self):
        assert _is_image_ext("noext") is False


class TestWalkImages:
    def test_finds_images_recursively(self, image_tree):
        results = sorted(_walk_images(str(image_tree)))
        names = [os.path.basename(p) for p in results]
        assert "a.png" in names
        assert "b.gif" in names
        assert "d.PNG" in names
        assert "c.txt" not in names
        assert "e.jpg" not in names

    def test_returns_full_paths(self, image_tree):
        results = list(_walk_images(str(image_tree)))
        for p in results:
            assert os.path.isabs(p)
            assert os.path.exists(p)

    def test_skips_symlinks_by_default(self, image_tree):
        # Create a symlink to a.png
        link = image_tree / "link.png"
        link.symlink_to(image_tree / "a.png")
        results = list(_walk_images(str(image_tree), follow_symlinks=False))
        names = [os.path.basename(p) for p in results]
        assert "link.png" not in names

    def test_follows_symlinks_when_requested(self, image_tree):
        link = image_tree / "link.png"
        link.symlink_to(image_tree / "a.png")
        results = list(_walk_images(str(image_tree), follow_symlinks=True))
        names = [os.path.basename(p) for p in results]
        assert "link.png" in names

    def test_permission_denied(self, image_tree):
        restricted = image_tree / "noaccess"
        restricted.mkdir()
        (restricted / "secret.png").write_bytes(b"data")
        restricted.chmod(0o000)
        try:
            results = list(_walk_images(str(image_tree)))
            # Should still get the other files, just skip the restricted dir
            names = [os.path.basename(p) for p in results]
            assert "secret.png" not in names
            assert "a.png" in names
        finally:
            restricted.chmod(0o755)

    def test_empty_directory(self, tmp_path):
        assert list(_walk_images(str(tmp_path))) == []


class TestCollectFiles:
    def test_sorted_by_default(self, image_tree):
        files = _collect_files(str(image_tree))
        assert files == sorted(files)
        assert len(files) == 3  # a.png, b.gif, sub/d.PNG

    def test_limit(self, image_tree):
        files = _collect_files(str(image_tree), limit=2)
        assert len(files) == 2

    def test_done_paths_filtering(self, image_tree):
        all_files = _collect_files(str(image_tree))
        # Mark the first file as done
        done = {all_files[0]}
        remaining = _collect_files(str(image_tree), done_paths=done)
        assert len(remaining) == len(all_files) - 1
        assert all_files[0] not in remaining

    def test_done_paths_with_limit(self, image_tree):
        all_files = _collect_files(str(image_tree))
        done = {all_files[0]}
        remaining = _collect_files(str(image_tree), done_paths=done, limit=1)
        assert len(remaining) == 1
        assert remaining[0] != all_files[0]

    def test_empty_done_paths_returns_all(self, image_tree):
        # Empty set is falsy, should take the non-resume path
        files_no_done = _collect_files(str(image_tree))
        files_empty_done = _collect_files(str(image_tree), done_paths=set())
        assert sorted(files_no_done) == sorted(files_empty_done)


class TestLoadDonePaths:
    def test_nonexistent_file(self, tmp_path):
        result = _load_done_paths(str(tmp_path / "nope.jsonl"))
        assert result == set()

    def test_reads_filepaths(self, tmp_path):
        jsonl = tmp_path / "done.jsonl"
        records = [
            {"filepath": "/data/img1.png", "risk_level": "low"},
            {"filepath": "/data/img2.png", "risk_level": "high"},
        ]
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        result = _load_done_paths(str(jsonl))
        assert result == {"/data/img1.png", "/data/img2.png"}

    def test_skips_corrupted_lines(self, tmp_path):
        jsonl = tmp_path / "done.jsonl"
        jsonl.write_text(
            '{"filepath": "/data/ok.png"}\n'
            'not valid json\n'
            '{"filepath": "/data/ok2.png"}\n'
        )
        result = _load_done_paths(str(jsonl))
        assert result == {"/data/ok.png", "/data/ok2.png"}

    def test_no_realpath_called(self, tmp_path):
        """Verify paths are stored verbatim without realpath resolution."""
        jsonl = tmp_path / "done.jsonl"
        # Use a path that would change under realpath (relative-looking but stored as-is)
        jsonl.write_text('{"filepath": "/some/path/./file.png"}\n')
        result = _load_done_paths(str(jsonl))
        assert "/some/path/./file.png" in result
