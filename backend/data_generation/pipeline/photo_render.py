"""Procedural stand-in photos of a car's rear seat, one look per damage tier.

Synthetic, not sourced, and labelled as such (Data Sources doc §2 decision #3: real or
stock photos per tier would be ideal; the handbook allows simulated data where real
sources are unavailable). Each tier draws what the Policy doc's tier describes, so the
Image Analysis tool has something real to look at:

- none: a clean seat (for testing claims the photo doesn't support)
- minor: a small drink spill (Policy §4, minor: spills)
- moderate: mud and dirt stains across the cushion (moderate: stains, dirt)
- severe: vomit (severe: vomit / bodily fluids)

Deterministic per (severity, seed), so a re-run produces identical bytes and hashes.
"""

import io
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 960, 640
SEVERITIES = ("none", "minor", "moderate", "severe")


def _blob(rng: random.Random, cx: float, cy: float, r: float, points: int = 28, jag: float = 0.35):
    out = []
    phase = rng.random() * math.tau
    for i in range(points):
        a = math.tau * i / points
        k = 1 + jag * (math.sin(3 * a + phase) * 0.5 + rng.uniform(-0.5, 0.5))
        out.append((cx + math.cos(a) * r * k * 1.35, cy + math.sin(a) * r * k * 0.75))
    return out


def _seat(rng: random.Random) -> Image.Image:
    img = Image.new("RGB", (W, H), (34, 36, 40))
    d = ImageDraw.Draw(img)
    # floor mat and door shadow
    d.rectangle((0, 520, W, H), fill=(24, 25, 28))
    # backrest
    d.rounded_rectangle((70, 20, 890, 300), 60, fill=(66, 70, 78))
    # cushion, seen slightly from above
    d.polygon([(40, 300), (920, 300), (960, 540), (0, 540)], fill=(74, 78, 87))
    # seams dividing the bench into three seats, and stitching rows
    for x in (340, 620):
        d.line((x, 30, x, 295), fill=(48, 51, 58), width=6)
        d.line((x + (x - 480) * 0.15, 305, x + (x - 480) * 0.35, 535), fill=(52, 55, 62), width=6)
    for y in (90, 170, 240):
        d.line((90, y, 870, y), fill=(58, 62, 70), width=2)
    d.line((40, 300, 920, 300), fill=(44, 47, 53), width=8)
    # headrests
    for x in (150, 420, 690):
        d.rounded_rectangle((x, -30, x + 120, 40), 22, fill=(60, 64, 72))
    # seat belt buckles
    for x in (330, 610):
        d.rounded_rectangle((x, 290, x + 22, 330), 5, fill=(20, 20, 22))
    # fabric grain
    noise = Image.effect_noise((W, H), 18).convert("RGB")
    img = ImageChops.add(img, noise, scale=1.0, offset=-60)
    return img


def _spill(img: Image.Image, rng: random.Random) -> None:
    """A knocked-over takeaway coffee: the cup on its side, a wet trail from its lid, and
    one glossy puddle with a darker rim. Small, in one spot: the minor tier."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = rng.uniform(440, 520), rng.uniform(400, 430)
    shape = _blob(rng, cx, cy, 62, jag=0.25)
    d.polygon(shape, fill=(120, 74, 36, 175))
    d.line(shape + shape[:1], fill=(78, 46, 22, 220), width=4)
    # trail from the cup's mouth into the puddle
    d.line((cx + 70, cy - 10, cx + 150, cy - 40), fill=(120, 74, 36, 190), width=22)
    # glossy highlights: it's still wet
    for _ in range(5):
        x, y = cx + rng.uniform(-50, 40), cy + rng.uniform(-22, 12)
        d.ellipse((x, y, x + rng.uniform(18, 34), y + rng.uniform(4, 8)), fill=(255, 245, 230, 120))
    # takeaway cup on its side: tapered white body, brown sleeve, black lid at the mouth
    x0, y0 = cx + 150, cy - 70
    d.polygon(
        [(x0, y0), (x0 + 120, y0 - 12), (x0 + 120, y0 + 72), (x0, y0 + 60)],
        fill=(236, 234, 228, 255),
    )
    d.polygon(
        [(x0 + 40, y0 - 4), (x0 + 85, y0 - 8), (x0 + 85, y0 + 68), (x0 + 40, y0 + 64)],
        fill=(150, 104, 62, 255),
    )
    d.rounded_rectangle((x0 - 14, y0 - 6, x0 + 6, y0 + 66), 6, fill=(25, 25, 25, 255))
    soft = layer.filter(ImageFilter.GaussianBlur(1.0))
    img.paste(soft, (0, 0), soft)


def _boot_print(d: ImageDraw.ImageDraw, x: float, y: float, colour: tuple, gap: tuple) -> None:
    d.rounded_rectangle((x, y, x + 56, y + 78), 26, fill=colour)  # forefoot
    d.rounded_rectangle((x + 8, y + 88, x + 50, y + 128), 18, fill=colour)  # heel
    for k in range(5):  # tread lugs
        d.line((x + 6, y + 10 + k * 14, x + 50, y + 16 + k * 14), fill=gap, width=5)
    for k in range(2):
        d.line((x + 12, y + 98 + k * 14, x + 46, y + 98 + k * 14), fill=gap, width=5)


def _mud(img: Image.Image, rng: random.Random) -> None:
    """Mud: dry dirt tracked in on boots (tread prints), clods, dust and grit across the
    cushion and footwell, in the grey-brown of dried soil rather than a liquid's sheen."""
    d = ImageDraw.Draw(img)
    soil, gap = (88, 76, 60), (64, 66, 72)
    for _ in range(9000):  # dust haze, densest where the boots went
        x, y = rng.gauss(480, 230), rng.gauss(450, 70)
        if 0 < x < W and 300 < y < H:
            r = rng.uniform(0.8, 2.2)
            shade = rng.randint(80, 118)
            d.ellipse(
                (x - r, y - r, x + r, y + r), fill=(shade, int(shade * 0.87), int(shade * 0.7))
            )
    for i in range(4):
        x, y = 150 + i * 190 + rng.uniform(-20, 20), (330 if i % 2 else 430) + rng.uniform(-20, 20)
        _boot_print(d, x, y, soil, gap)
    for _ in range(45):  # clods: lit from above, shadow below
        x, y = rng.uniform(80, 880), rng.uniform(320, 610)
        s = rng.uniform(6, 16)
        d.polygon(_blob(rng, x + 2, y + 3, s, points=9, jag=0.8), fill=(40, 34, 28))
        d.polygon(_blob(rng, x, y, s, points=9, jag=0.8), fill=(104, 90, 70))
        d.polygon(
            _blob(rng, x - s * 0.3, y - s * 0.3, s * 0.4, points=6, jag=0.5), fill=(130, 114, 90)
        )
    for _ in range(3):  # scuffs on the backrest
        x, y = rng.uniform(150, 750), rng.uniform(140, 260)
        for _k in range(160):
            px_, py_ = x + rng.uniform(0, 130), y + rng.gauss(0, 7)
            d.point((px_, py_), fill=soil)


def _vomit(img: Image.Image, rng: random.Random) -> None:
    """Vomit: a large lumpy yellow-orange pool with chunks, running off the cushion edge
    onto the floor, with splatter."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = rng.uniform(440, 520), rng.uniform(410, 440)
    d.polygon(_blob(rng, cx, cy, 150, points=40, jag=0.45), fill=(196, 160, 72, 235))
    d.polygon(_blob(rng, cx + 60, cy + 120, 70, jag=0.5), fill=(188, 150, 66, 235))
    d.polygon(_blob(rng, cx + 70, cy + 170, 90, jag=0.5), fill=(180, 142, 60, 235))
    palette = [
        (214, 178, 92),
        (166, 128, 52),
        (226, 196, 120),
        (140, 150, 60),
        (200, 120, 60),
        (235, 220, 170),
    ]
    for _ in range(420):  # chunks
        a, r = rng.uniform(0, math.tau), abs(rng.gauss(0, 85))
        x, y = cx + math.cos(a) * r * 1.4, cy + math.sin(a) * r * 0.7
        s = rng.uniform(3, 11)
        d.polygon(_blob(rng, x, y, s, points=8, jag=0.7), fill=(*rng.choice(palette), 255))
    for _ in range(60):  # splatter
        a, r = rng.uniform(0, math.tau), rng.uniform(170, 320)
        x, y = cx + math.cos(a) * r * 1.3, cy + math.sin(a) * r * 0.55
        s = rng.uniform(4, 13)
        d.ellipse((x - s, y - s * 0.7, x + s, y + s * 0.7), fill=(196, 160, 72, 220))
    for _ in range(40):  # wet highlights
        x, y = cx + rng.gauss(0, 110), cy + rng.gauss(0, 45)
        d.ellipse((x - 6, y - 2, x + 6, y + 2), fill=(255, 250, 225, 140))
    soft = layer.filter(ImageFilter.GaussianBlur(0.8))
    img.paste(soft, (0, 0), soft)


def render_seat_photo(severity: str, seed: int = 0) -> bytes:
    """JPEG bytes of a rear seat in the given state."""
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}")
    rng = random.Random(f"{severity}:{seed}")
    img = _seat(rng)
    {"none": lambda *_: None, "minor": _spill, "moderate": _mud, "severe": _vomit}[severity](
        img, rng
    )
    # camera: slight blur, vignette
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    vignette = Image.radial_gradient("L").resize(img.size).point(lambda v: int(v * 0.55))
    img = ImageChops.subtract(img, Image.merge("RGB", (vignette,) * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=86)
    return buf.getvalue()
