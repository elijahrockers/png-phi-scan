"""CLI entry point for PNG/GIF PHI scanning."""

import argparse
import gc
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import FileError, PixelPHIFinding, ScanReport
from .scanner import scan_file

logger = logging.getLogger(__name__)


class ScanTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise ScanTimeout()


@contextmanager
def _file_timeout(seconds: int | None):
    """Set and clear a SIGALRM-based per-file timeout."""
    if seconds:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(seconds)
    try:
        yield
    finally:
        if seconds:
            signal.alarm(0)


def _is_image_ext(filename: str) -> bool:
    """Check if a filename has a supported image extension (string-based, no Path)."""
    lower = filename.lower()
    return lower.endswith(".png") or lower.endswith(".gif")


def _walk_images(root: str, follow_symlinks: bool = False) -> Iterator[str]:
    """Recursively yield image file paths using os.scandir().

    On Linux, DirEntry.is_file() and is_symlink() read from the d_type field
    in the getdents() buffer — zero extra syscalls. This is critical for NFS
    directories with millions of files.
    """
    try:
        entries = os.scandir(root)
    except PermissionError:
        logger.warning("Permission denied: %s", root)
        return
    with entries:
        for entry in entries:
            if entry.is_file(follow_symlinks=follow_symlinks):
                if _is_image_ext(entry.name):
                    yield entry.path
            elif entry.is_dir(follow_symlinks=follow_symlinks):
                yield from _walk_images(entry.path, follow_symlinks)


def _load_done_paths(output_file: str) -> set[str]:
    """Read an existing JSONL output and return paths already scanned."""
    done: set[str] = set()
    path = Path(output_file)
    if not path.exists():
        return done
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                raw_path = record.get("filepath", "")
                if raw_path:
                    done.add(raw_path)
            except json.JSONDecodeError:
                logger.warning(
                    "Skipping corrupted line %d in %s", line_no, output_file,
                )
    return done


CHECKPOINT_INTERVAL = 500_000


def _collect_files(
    directory: str,
    follow_symlinks: bool = False,
    limit: int | None = None,
    done_paths: set[str] | None = None,
) -> list[str]:
    """Recursively collect image files from a directory using os.scandir()."""
    files: list[str] = []
    visited = 0
    for p in _walk_images(directory, follow_symlinks):
        visited += 1
        if visited % CHECKPOINT_INTERVAL == 0:
            print(f"[checkpoint]   ...visited {visited} image files")
        if done_paths is not None:
            canonical = os.path.realpath(p) if follow_symlinks else p
            if canonical in done_paths:
                continue
        files.append(p)
        if limit is not None and len(files) >= limit:
            break
    if done_paths is not None:
        print(
            f"[checkpoint]   ...visited {visited} total,"
            f" {len(files)} remaining after resume filter"
        )
        return files
    if limit is not None:
        return files
    return sorted(files)


def _collect_manifest(
    manifest_path: Path,
    chunk_size: int | None = None,
    chunk_index: int | None = None,
    limit: int | None = None,
) -> list[Path]:
    """Read file paths from a manifest (one per line), optionally chunked."""
    lines = manifest_path.read_text().strip().splitlines()
    paths = [Path(line.strip()) for line in lines if line.strip()]

    if chunk_size is not None and chunk_index is not None:
        total_paths = len(paths)
        start = chunk_index * chunk_size
        paths = paths[start : start + chunk_size]
        if not paths and start >= total_paths:
            logger.warning(
                "Chunk index %d (start=%d) is past end of manifest (%d files)",
                chunk_index, start, total_paths,
            )

    if limit is not None:
        paths = paths[:limit]
    return paths


def _format_finding(f: PixelPHIFinding, n_frames: int, indent: str = "  ") -> str:
    """Format a single finding as a human-readable string."""
    frame_info = f" frame={f.frame_index}" if n_frames > 1 else ""
    return (
        f"{indent}[{f.severity.value.upper()}] \"{f.text}\""
        f" at ({f.bbox.x},{f.bbox.y}) {f.bbox.width}x{f.bbox.height}"
        f" conf={f.confidence:.0%}{frame_info}"
    )


def _print_file_findings(report: ScanReport, index: int, total: int, short_path: str) -> None:
    """Print condensed per-file findings during batch scan."""
    phi_count = report.total_phi_count
    risk = report.risk_level.value.upper()

    status = f"{risk} ({phi_count} findings)" if phi_count > 0 else "CLEAN"
    print(f"\n[{index}/{total}] {short_path} -- {status}")

    if report.pixel_findings:
        print(f"  Pixel text ({len(report.pixel_findings)}):")
        for f in report.pixel_findings:
            print(_format_finding(f, report.n_frames, indent="    "))


def _print_summary(report: ScanReport) -> None:
    """Print a human-readable summary for single-file mode."""
    risk = report.risk_level.value

    print(f"\n{'=' * 60}")
    print("PNG/GIF PHI Scan Report")
    print(f"{'=' * 60}")
    print(f"File: {report.filepath}")
    print(f"Dimensions: {report.image_width}x{report.image_height}")
    print(f"Frames: {report.n_frames}")
    print(f"Risk Level: {risk.upper()}")
    print(f"Total PHI Findings: {report.total_phi_count}")
    print()

    if report.pixel_findings:
        print(f"--- Pixel Findings ({len(report.pixel_findings)}) ---")
        for f in report.pixel_findings:
            print(_format_finding(f, report.n_frames))
        print()

    if report.recommendations:
        print("Recommendations:")
        for r in report.recommendations:
            print(f"  - {r}")

    print(f"{'=' * 60}\n")


def _print_batch_summary(
    source: str,
    total: int,
    files_with_phi: int,
    files_clean: int,
    files_errored: int,
    risk_counts: dict[str, int],
    total_pixel_findings: int,
    pixel_text_counts: dict[str, int],
    error_list: list[tuple[str, str]],
    output_file: str | None,
) -> None:
    """Print aggregate batch summary to console."""
    print("\n" + "=" * 72)
    print("BATCH SCAN SUMMARY")
    print("=" * 72)

    print(f"\nSource:         {source}")
    print(f"Files scanned:  {total}")
    print(f"Files with PHI: {files_with_phi}")
    print(f"Files clean:    {files_clean}")
    print(f"Files errored:  {files_errored}")

    print("\nRisk breakdown:")
    for level in ["high", "medium", "low"]:
        print(f"  {level.upper():8s} {risk_counts.get(level, 0)}")

    print(f"\nFindings: {total_pixel_findings} pixel texts")

    if pixel_text_counts:
        print("\nTop pixel text detections:")
        for text, count in sorted(pixel_text_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {count:4d}x  \"{text}\"")

    if error_list:
        print("\nErrors:")
        for fp, err in error_list:
            print(f"  {fp}: {err}")

    if output_file:
        print(f"\nReport: {output_file}")

    print("=" * 72)
    print()


def _scan_single(
    filepath: str, output_file: str | None, timeout: int | None = None,
    max_frames: int = 50, batch_size: int = 16,
) -> int:
    """Scan a single file, print summary, write JSON report."""
    with _file_timeout(timeout):
        report = scan_file(filepath, max_frames=max_frames, batch_size=batch_size)

    _print_summary(report)

    report_json = report.model_dump_json(indent=2)
    if output_file:
        Path(output_file).write_text(report_json + "\n")
        print(f"Report written to {output_file}")
    else:
        print(report_json)

    return 1 if report.has_phi else 0


GC_INTERVAL = 500
FLUSH_INTERVAL = 100


def _scan_batch(
    files: list[str], source: str, output_file: str | None, verbose: bool,
    timeout: int | None = None, resume: bool = False, max_frames: int = 50,
    batch_size: int = 16,
) -> int:
    """Scan multiple files, print per-file findings and aggregate summary, write JSONL."""
    total = len(files)
    if total == 0:
        print("Nothing left to scan.")
        return 0
    print(f"\nScanning {total} files in {source} ...")
    if output_file:
        print(f"Writing JSONL report to {output_file}")
    print("=" * 72)

    # Aggregate stats
    files_with_phi = 0
    files_clean = 0
    files_errored = 0
    error_list: list[tuple[str, str]] = []
    risk_counts: defaultdict[str, int] = defaultdict(int)
    pixel_text_counts: defaultdict[str, int] = defaultdict(int)
    total_pixel_findings = 0

    mode = "a" if resume else "w"
    out = open(output_file, mode) if output_file else None  # noqa: SIM115
    try:
        for i, filepath in enumerate(files, 1):
            parent_name = os.path.basename(os.path.dirname(filepath))
            short_path = f"{parent_name}/{os.path.basename(filepath)}"

            try:
                with _file_timeout(timeout):
                    try:
                        report = scan_file(
                            filepath, max_frames=max_frames, batch_size=batch_size,
                        )
                    except ScanTimeout:
                        raise ScanTimeout(f"Timed out after {timeout}s")
            except Exception as exc:
                files_errored += 1
                error_list.append((filepath, str(exc)))
                print(f"\n[{i}/{total}] {short_path} -- ERROR: {exc}")
                if out:
                    error = FileError(filepath=filepath, error=str(exc))
                    out.write(error.model_dump_json() + "\n")
                    out.flush()
                if i % GC_INTERVAL == 0:
                    gc.collect()
                continue

            # Print per-file findings
            _print_file_findings(report, i, total, short_path)

            # Stream to JSONL (buffered flush)
            if out:
                out.write(report.model_dump_json() + "\n")
                if i % FLUSH_INTERVAL == 0:
                    out.flush()

            # Accumulate stats
            risk_counts[report.risk_level.value] += 1
            if report.has_phi:
                files_with_phi += 1
            else:
                files_clean += 1

            total_pixel_findings += len(report.pixel_findings)
            for f in report.pixel_findings:
                pixel_text_counts[f.text] += 1

            # Periodic GC instead of per-file
            if i % GC_INTERVAL == 0:
                gc.collect()
    finally:
        if out:
            out.close()

    _print_batch_summary(
        source=source,
        total=total,
        files_with_phi=files_with_phi,
        files_clean=files_clean,
        files_errored=files_errored,
        risk_counts=risk_counts,
        total_pixel_findings=total_pixel_findings,
        pixel_text_counts=pixel_text_counts,
        error_list=error_list,
        output_file=output_file,
    )

    if files_errored > 0:
        return 2
    return 1 if files_with_phi > 0 else 0


def main():
    parser = argparse.ArgumentParser(
        description="PNG/GIF PHI Scanner — scan images for protected health information",
        epilog=(
            "examples:\n"
            "  png-phi-scan image.png -o report.json\n"
            "  png-phi-scan --dir ./images -o results.jsonl\n"
            "  png-phi-scan --manifest files.txt --chunk-size 100 --chunk-index 0 -o out.jsonl\n"
            "  png-phi-scan --dir ./images -o results.jsonl --resume\n"
            "\n"
            "query the JSONL report:\n"
            "  jq 'select(.risk_level == \"high\") | .filepath' results.jsonl\n"
            "\n"
            "exit codes:\n"
            "  0  all files clean (no PHI, no errors)\n"
            "  1  PHI detected in one or more files\n"
            "  2  one or more files produced errors\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("filepath", nargs="?", default=None,
                        help="Path to a single image file (.png or .gif)")
    parser.add_argument("--dir", dest="directory",
                        help="Recursively scan directory for image files")
    parser.add_argument("--manifest", dest="manifest",
                        help="File containing one image path per line")
    parser.add_argument("--chunk-size", type=int, default=None,
                        help="Number of files per chunk (for SLURM array jobs)")
    parser.add_argument("--chunk-index", type=int, default=None,
                        help="Zero-based chunk index to process")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of files to scan (default: all)")
    parser.add_argument("-o", "--output", dest="output_file", default=None,
                        help="Write report to file (single: JSON, batch: JSONL)")
    parser.add_argument("-L", "--follow-symlinks", dest="follow_symlinks",
                        action="store_true",
                        help="Follow symbolic links when scanning directories")
    parser.add_argument("--max-frames", type=int, default=50,
                        help="Maximum GIF frames to scan (default: 50)")
    parser.add_argument("--timeout", type=int, default=None,
                        help="Per-file timeout in seconds (default: no timeout)")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU for OCR even if GPU is available")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="EasyOCR recognition batch size (default: 16, higher = faster on GPU)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume interrupted batch scan; skip files already in output JSONL")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Validate mutually exclusive modes
    modes = sum(1 for x in [args.filepath, args.directory, args.manifest] if x is not None)
    if modes == 0:
        parser.error("Provide a filepath, --dir, or --manifest")
    if modes > 1:
        parser.error("Specify only one of: filepath, --dir, --manifest")

    # Validate --resume
    if args.resume:
        if not args.output_file:
            parser.error("--resume requires -o/--output")
        if args.filepath:
            parser.error("--resume is only supported in batch mode (--dir or --manifest)")

    t0 = time.monotonic()
    print(f"[checkpoint] Args parsed at +{time.monotonic() - t0:.1f}s")

    # Load done_paths early so _collect_files can filter during streaming
    done_paths: set[str] = set()
    if args.resume and args.output_file:
        print("[checkpoint] Loading completed paths from output...")
        t_done = time.monotonic()
        done_paths = _load_done_paths(args.output_file)
        print(
            f"[checkpoint] Loaded {len(done_paths)} completed paths"
            f" in {time.monotonic() - t_done:.1f}s"
        )

    # Collect files first (before heavy OCR init)
    files = None
    source = None
    if args.directory:
        dirpath = Path(args.directory)
        if not dirpath.is_dir():
            parser.error(f"Not a directory: {args.directory}")
        # Resolve once so all walked paths start from the canonical root
        canonical_dir = os.path.realpath(args.directory)
        print(f"[checkpoint] Collecting files from {canonical_dir}...")
        t_collect = time.monotonic()
        files = _collect_files(
            canonical_dir, args.follow_symlinks, args.limit, done_paths=done_paths,
        )
        print(
            f"[checkpoint] Collected {len(files)} files in"
            f" {time.monotonic() - t_collect:.1f}s"
        )
        source = args.directory
    elif args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_file():
            parser.error(f"Manifest not found: {args.manifest}")
        manifest_paths = _collect_manifest(
            manifest_path, args.chunk_size, args.chunk_index, args.limit,
        )
        files = [os.path.realpath(str(p)) for p in manifest_paths]
        source = args.manifest

    if files is not None and not files:
        logger.warning("No image files found")
        sys.exit(0)

    # Initialize OCR reader (heavy — loads torch + easyocr)
    from .ocr_reader import init_reader

    print("[checkpoint] Initializing EasyOCR model...")
    t_ocr = time.monotonic()
    init_reader(gpu=False if args.cpu else None)
    device = "GPU" if not args.cpu else "CPU"
    print(f"[checkpoint] EasyOCR ready ({device}) in {time.monotonic() - t_ocr:.1f}s")

    # Single file mode
    if args.filepath:
        try:
            exit_code = _scan_single(
                args.filepath, args.output_file, args.timeout, args.max_frames,
                args.batch_size,
            )
        except Exception as exc:
            logger.error("Failed to scan %s: %s", args.filepath, exc)
            sys.exit(2)
        sys.exit(exit_code)

    # Batch modes
    exit_code = _scan_batch(
        files, source, args.output_file, args.verbose,
        args.timeout, args.resume, args.max_frames, args.batch_size,
    )
    sys.exit(exit_code)
