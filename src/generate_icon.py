"""The app icon: the GUI's Launchpad arrow on the GUI's own background.

    python src/generate_icon.py      writes assets/launcher.ico (+ launcher.png preview)

build.bat runs this before PyInstaller, so the exe gets the icon. gui.py also uses
render() for the system tray icon, so every place the app shows up looks the same.

Design (matches ui/style.css):
    background  the window gradient  #0a1628 -> #1a2a3f -> #2d1b45 (135 deg)
    arrow       the sidebar "Launchpad" logo, in the Add app button cyan #4CC2FF -> #2a9dd5
    edge        a faint cyan border, like the cards and buttons
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICO_PATH = ROOT / "assets" / "launcher.ico"
PNG_PATH = ROOT / "assets" / "launcher.png"
SIZES = (16, 24, 32, 48, 64, 128, 256)

BG_STOPS = ((0.0, (10, 22, 40)), (0.25, (26, 42, 63)), (0.75, (45, 27, 69)), (1.0, (31, 37, 50)))
CYAN_TOP = (76, 194, 255)      # #4CC2FF
CYAN_BOTTOM = (42, 157, 213)   # #2a9dd5
# The sidebar logo path "M3 15l20-9-7 16-3-7z" (26 x 26 viewBox) as points
ARROW = ((3, 15), (23, 6), (16, 22), (13, 15))


def _gradient(size, stops):
    """Diagonal (135 deg, top-left to bottom-right) multi-stop gradient."""
    small = 64   # build small, then scale: smooth and fast
    img = Image.new("RGB", (small, small))
    px = img.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                    px[x, y] = tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
                    break
    return img.resize((size, size), Image.BICUBIC)


def _vertical(size, top, bottom):
    img = Image.new("RGB", (1, 2))
    img.putpixel((0, 0), top)
    img.putpixel((0, 1), bottom)
    return img.resize((size, size), Image.BILINEAR)


def render(size):
    """The icon as an RGBA image of size x size pixels."""
    tiny = size <= 24                     # 16/24 px: bigger arrow, no glow or border
    s = max(size * 8, 512)                # draw large, then downscale (anti-aliasing)
    margin = 0 if tiny else round(s * 0.04)
    radius = round(s * (0.18 if tiny else 0.22))

    # Rounded square with the window's gradient
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((margin, margin, s - 1 - margin, s - 1 - margin),
                                           radius=radius, fill=255)
    icon = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    icon.paste(_gradient(s, BG_STOPS), (0, 0), mask)

    # Arrow: logo points scaled into the square, centred on the shape's middle
    span = (0.80 if tiny else 0.62) * (s - 2 * margin)   # width of the arrow (20 logo units)
    unit = span / 20
    cx, cy = (3 + 23) / 2, (6 + 22) / 2
    pts = [(s / 2 + (x - cx) * unit, s / 2 + (y - cy) * unit + s * 0.01) for x, y in ARROW]

    arrow_mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(arrow_mask)
    d.polygon(pts, fill=255)
    # Round the corners the way the logo's stroke-linejoin="round" does
    join = max(2, round(unit * 1.6))
    d.line(pts + [pts[0]], fill=255, width=join, joint="curve")
    for x, y in pts:
        d.ellipse((x - join / 2, y - join / 2, x + join / 2, y + join / 2), fill=255)

    if not tiny:
        # Soft cyan glow under the arrow, like the Add app button's shadow
        glow = Image.new("RGBA", (s, s), CYAN_TOP + (0,))
        glow.putalpha(arrow_mask.filter(ImageFilter.GaussianBlur(s * 0.045)).point(lambda a: a * 0.55))
        icon.alpha_composite(Image.composite(glow, Image.new("RGBA", (s, s)), mask))

    arrow = _vertical(s, CYAN_TOP, CYAN_BOTTOM).convert("RGBA")
    arrow.putalpha(arrow_mask)
    icon.alpha_composite(arrow)

    # The fold line of the arrow (logo: tip -> notch), in the background colour
    fold = Image.new("L", (s, s), 0)
    ImageDraw.Draw(fold).line((pts[1], pts[3]), fill=255, width=max(2, round(unit * 0.9)))
    fold = Image.composite(fold, Image.new("L", (s, s), 0), arrow_mask)
    shade = Image.new("RGBA", (s, s), (10, 22, 40, 0))
    shade.putalpha(fold.point(lambda a: a * 0.55))
    icon.alpha_composite(shade)

    if not tiny:
        # Faint cyan edge, like the cards and buttons
        edge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            (margin, margin, s - 1 - margin, s - 1 - margin), radius=radius,
            outline=(76, 194, 255, 90), width=max(2, round(s * 0.012)))
        icon.alpha_composite(edge)

    return icon.resize((size, size), Image.LANCZOS)


def write_icon():
    images = [render(n) for n in SIZES]
    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(ICO_PATH, format="ICO", sizes=[(n, n) for n in SIZES],
                    append_images=images[:-1])
    images[-1].save(PNG_PATH)
    print(f"Created {ICO_PATH}")


if __name__ == "__main__":
    write_icon()
