"""Create synthetic PNG/GIF test fixtures with intentionally planted fake PHI.

All data is entirely synthetic — no real patient information is used.

Usage:
    python fixtures/create_test_fixtures.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_font(size: int = 20):
    """Load a readable font, falling back to default."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
    except OSError:
        return ImageFont.load_default()


def create_clean_png():
    """Create a clean PNG with no text — solid color with a gradient."""
    filepath = os.path.join(FIXTURES_DIR, "test_clean.png")
    img = Image.new("RGB", (256, 256), (30, 30, 60))
    draw = ImageDraw.Draw(img)
    # Draw some geometric shapes (no text)
    draw.ellipse([60, 60, 196, 196], fill=(80, 80, 120))
    draw.rectangle([100, 100, 156, 156], fill=(50, 50, 90))
    img.save(filepath)
    print(f"Created: {filepath}")


def create_phi_text_png():
    """Create a PNG with fake PHI burned into pixel data."""
    filepath = os.path.join(FIXTURES_DIR, "test_phi_text.png")
    font = _get_font(20)

    img = Image.new("RGB", (400, 300), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Burn in fake PHI text
    draw.text((10, 10), "SMITH, JOHN A", fill=(255, 255, 255), font=font)
    draw.text((10, 40), "MRN: 9876543", fill=(255, 255, 255), font=font)
    draw.text((10, 70), "DOB: 1985-03-15", fill=(200, 200, 200), font=font)
    draw.text((10, 100), "Houston Methodist", fill=(200, 200, 200), font=font)

    img.save(filepath)
    print(f"Created: {filepath}")


def create_clean_gif():
    """Create a 3-frame animated GIF with no text."""
    filepath = os.path.join(FIXTURES_DIR, "test_clean.gif")
    frames = []
    colors = [(30, 30, 60), (60, 30, 30), (30, 60, 30)]
    for color in colors:
        frame = Image.new("RGB", (256, 256), color)
        draw = ImageDraw.Draw(frame)
        draw.ellipse([60, 60, 196, 196], fill=tuple(c + 50 for c in color))
        frames.append(frame)

    frames[0].save(
        filepath,
        save_all=True,
        append_images=frames[1:],
        duration=500,
        loop=0,
    )
    print(f"Created: {filepath}")


def create_phi_text_gif():
    """Create a 3-frame animated GIF with fake PHI on frame 0."""
    filepath = os.path.join(FIXTURES_DIR, "test_phi_text.gif")
    font = _get_font(20)
    frames = []

    # Frame 0: has PHI text
    frame0 = Image.new("RGB", (400, 300), (0, 0, 0))
    draw = ImageDraw.Draw(frame0)
    draw.text((10, 10), "SMITH, JOHN A", fill=(255, 255, 255), font=font)
    draw.text((10, 40), "MRN: 9876543", fill=(255, 255, 255), font=font)
    frames.append(frame0)

    # Frames 1-2: clean
    for i in range(2):
        frame = Image.new("RGB", (400, 300), (20 * (i + 1), 20 * (i + 1), 40))
        draw = ImageDraw.Draw(frame)
        draw.ellipse([100, 50, 300, 250], fill=(60, 60, 100))
        frames.append(frame)

    frames[0].save(
        filepath,
        save_all=True,
        append_images=frames[1:],
        duration=500,
        loop=0,
    )
    print(f"Created: {filepath}")


if __name__ == "__main__":
    create_clean_png()
    create_phi_text_png()
    create_clean_gif()
    create_phi_text_gif()
    print("All fixtures created.")
