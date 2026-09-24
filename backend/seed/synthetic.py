"""Synthetic packaging label generator.

Produces label images with *known ground truth*, which is what makes the
preprocessing and rules engine testable rather than merely runnable: if the
generator printed "MRP Rs. 45.00" at a known 2.4 mm cap height and then applied a
known perspective warp, the pipeline's output can be checked against fact
instead of eyeballed.

Also supplies the demo corpus with real pack images, including deliberately
non-compliant ones so a demo can show violations being caught rather than
described.

    python -m seed.synthetic --out ../storage/uploads/demo --count 6
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import cv2

    _CV2 = True
except ImportError:  # pragma: no cover
    _CV2 = False


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------
@dataclass
class PackSpec:
    """What the generator printed -- the answer key for a test."""

    brand: str
    product: str
    mrp: float
    net_qty_value: float
    net_qty_unit: str
    mfg_date: str
    expiry_date: str
    manufacturer: str
    address: str
    country: str
    customer_care: str
    fssai: str | None
    barcode: str
    pack_width_cm: float
    pack_height_cm: float
    # Declarations deliberately omitted, e.g. {"unit_price", "mfg_date"}
    omit: set[str] = field(default_factory=set)
    # Declarations printed below the Rule 11 minimum height
    undersize: set[str] = field(default_factory=set)
    curved: bool = False

    @property
    def unit_price(self) -> float:
        return self.mrp / self.net_qty_value if self.net_qty_value else 0.0

    def expected_fields(self) -> dict[str, str | None]:
        """What a correct extraction should return."""
        out: dict[str, str | None] = {
            "mrp": None if "mrp" in self.omit else f"{self.mrp:.2f}",
            "net_quantity": None if "net_quantity" in self.omit
            else f"{self.net_qty_value:g} {self.net_qty_unit}",
            "unit_price": None if "unit_price" in self.omit
            else f"{self.unit_price:.4f}/{self.net_qty_unit}",
            "mfg_date": None if "mfg_date" in self.omit else self.mfg_date,
            "expiry_date": None if "expiry_date" in self.omit else self.expiry_date,
            "manufacturer_name": None if "manufacturer_name" in self.omit else self.manufacturer,
            "manufacturer_address": None if "manufacturer_address" in self.omit else self.address,
            "country_of_origin": None if "country_of_origin" in self.omit else self.country,
            "customer_care": None if "customer_care" in self.omit else self.customer_care,
            "fssai_licence": None if "fssai_licence" in self.omit else self.fssai,
        }
        return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
# Rendered at a fixed pixel-per-mm so font heights are physically meaningful.
PX_PER_MM = 12.0


def _font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a real TrueType face; text metrics must be predictable."""
    candidates = (
        ["arialbd.ttf", "DejaVuSans-Bold.ttf", "seguisb.ttf"]
        if bold
        else ["arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"]
    )
    roots = [
        Path("C:/Windows/Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/Library/Fonts"),
    ]
    for name in candidates:
        for root in roots:
            p = root / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size_px)
                except Exception:
                    continue
    return ImageFont.load_default(size=size_px)


def mm_to_px(mm: float) -> int:
    """Cap height in mm -> font pixel size (cap height is ~70% of em)."""
    return max(6, int(round(mm * PX_PER_MM / 0.7)))


def _draw_barcode(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, code: str) -> None:
    """Render a barcode-like stripe pattern seeded by the digits.

    Not a scannable EAN-13 symbology -- it exists so contour analysis and the
    vision model see a realistic barcode block in the expected place.
    """
    rng = random.Random(code)
    draw.rectangle([x, y, x + w, y + h], fill="white")
    cursor = x + 4
    while cursor < x + w - 4:
        bar_w = rng.choice([1, 1, 2, 2, 3])
        if rng.random() < 0.55:
            draw.rectangle([cursor, y + 3, cursor + bar_w, y + h - 14], fill="black")
        cursor += bar_w + rng.choice([1, 2])
    draw.text((x + w // 2 - 42, y + h - 13), code, font=_font(11), fill="black")


def render_label(spec: PackSpec) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """Render a front+back label panel. Returns the image and per-field boxes."""
    w = int(spec.pack_width_cm * 10 * PX_PER_MM)
    h = int(spec.pack_height_cm * 10 * PX_PER_MM)
    img = Image.new("RGB", (w, h), (252, 250, 244))
    draw = ImageDraw.Draw(img)
    boxes: dict[str, tuple[int, int, int, int]] = {}

    accent = (
        random.Random(spec.brand).randint(20, 180),
        random.Random(spec.product).randint(20, 140),
        random.Random(spec.brand + spec.product).randint(60, 200),
    )

    # --- header band ---
    band_h = int(h * 0.20)
    draw.rectangle([0, 0, w, band_h], fill=accent)
    bf = _font(mm_to_px(7.0), bold=True)
    draw.text((int(w * 0.05), int(band_h * 0.18)), spec.brand, font=bf, fill="white")
    pf = _font(mm_to_px(4.5), bold=True)
    draw.text((int(w * 0.05), int(band_h * 0.58)), spec.product[:34], font=pf, fill="white")

    y = band_h + int(h * 0.04)
    left = int(w * 0.05)

    def put(key: str, text: str, mm: float, bold: bool = False, colour=(20, 20, 20)) -> None:
        nonlocal y
        if key in spec.omit:
            return
        size_mm = 1.4 if key in spec.undersize else mm
        f = _font(mm_to_px(size_mm), bold=bold)
        bbox = draw.textbbox((left, y), text, font=f)
        draw.text((left, y), text, font=f, fill=colour)
        boxes[key] = (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
        y = bbox[3] + int(h * 0.018)

    # --- principal declarations ---
    put("mrp", f"MRP Rs. {spec.mrp:.2f}", 4.0, bold=True)
    if "mrp" not in spec.omit:
        f = _font(mm_to_px(1.9))
        draw.text((left, y - int(h * 0.010)), "(Incl. of all taxes)", font=f, fill=(70, 70, 70))
        y += int(h * 0.018)

    put("net_quantity", f"Net Qty: {spec.net_qty_value:g} {spec.net_qty_unit}", 3.2, bold=True)
    put("unit_price",
        f"Unit Sale Price: Rs. {spec.unit_price:.4f} per {spec.net_qty_unit}", 2.2)
    put("mfg_date", f"Mfg Date: {spec.mfg_date}", 2.2)
    put("expiry_date", f"Best Before: {spec.expiry_date}", 2.2)
    put("manufacturer_name", f"Mfd by: {spec.manufacturer}", 2.2)
    put("manufacturer_address", spec.address, 1.9)
    put("country_of_origin", f"Country of Origin: {spec.country}", 2.2)
    put("customer_care", f"Consumer Care: {spec.customer_care}", 1.9)
    if spec.fssai:
        put("fssai_licence", f"FSSAI Lic. No. {spec.fssai}", 2.0)

    # --- barcode block, bottom right ---
    bw, bh = int(w * 0.42), int(h * 0.10)
    bx, by = w - bw - int(w * 0.05), h - bh - int(h * 0.04)
    _draw_barcode(draw, bx, by, bw, bh, spec.barcode)
    boxes["barcode"] = (bx, by, bw, bh)

    return img, boxes


# ---------------------------------------------------------------------------
# Distortions -- simulate a real handheld capture
# ---------------------------------------------------------------------------
def _counter_background(h: int, w: int, seed: int = 0) -> np.ndarray:
    """A surface the pack sits on -- shop counter, shelf or table.

    Deliberately mid-tone and textured. A near-white backdrop would be an
    unrealistically easy fixture: real inspection photographs always have a
    genuine tonal step between pack and surface, and testing against a fake
    that lacks one measures nothing useful.
    """
    rng = np.random.default_rng(seed)
    base = rng.integers(96, 150)
    canvas = np.full((h, w, 3), base, dtype=np.int16)

    # Slight colour cast, as wood or laminate has.
    canvas[..., 0] += int(rng.integers(-6, 18))
    canvas[..., 2] += int(rng.integers(-14, 6))

    # Broad lighting falloff plus fine grain.
    yy, xx = np.mgrid[0:h, 0:w]
    vignette = 1.0 - 0.12 * (((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2) * 4
    canvas = canvas * vignette[..., None]
    canvas += rng.normal(0, 5, canvas.shape)
    return np.clip(canvas, 0, 255).astype(np.uint8)


def apply_perspective(
    img: Image.Image, strength: float = 0.10, seed: int = 0
) -> tuple[Image.Image, np.ndarray]:
    """Photograph the flat label off-axis. Returns the image and true corners."""
    arr = np.array(img)
    h, w = arr.shape[:2]
    rng = random.Random(seed)

    pad_w, pad_h = int(w * 0.18), int(h * 0.18)
    canvas = _counter_background(h + 2 * pad_h, w + 2 * pad_w, seed=seed)

    def jitter() -> float:
        return rng.uniform(-strength, strength)

    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array(
        [
            [pad_w + w * jitter(), pad_h + h * jitter()],
            [pad_w + w * (1 + jitter()), pad_h + h * jitter()],
            [pad_w + w * (1 + jitter()), pad_h + h * (1 + jitter())],
            [pad_w + w * jitter(), pad_h + h * (1 + jitter())],
        ],
        dtype=np.float32,
    )

    if not _CV2:
        canvas[pad_h : pad_h + h, pad_w : pad_w + w] = arr
        return Image.fromarray(canvas), src

    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        arr, m, (canvas.shape[1], canvas.shape[0]),
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
    )
    mask = cv2.warpPerspective(
        np.full((h, w), 255, np.uint8), m, (canvas.shape[1], canvas.shape[0])
    )
    canvas[mask > 0] = warped[mask > 0]
    return Image.fromarray(canvas), dst


def apply_cylindrical(img: Image.Image, arc_deg: float = 140.0) -> Image.Image:
    """Wrap a flat label onto a cylinder -- the forward of what unwarp inverts."""
    arr = np.array(img)
    h, w = arr.shape[:2]
    if not _CV2:
        return img

    arc = math.radians(arc_deg)
    radius = (w / 2.0) / math.sin(arc / 2.0)
    out_w = int(2 * radius * math.sin(arc / 2.0))
    cx_out = out_w / 2.0

    # For each destination column, find which label column projects there.
    cols = np.arange(out_w, dtype=np.float32)
    sin_t = np.clip((cols - cx_out) / radius, -1.0, 1.0)
    theta = np.arcsin(sin_t)
    src_x = ((theta + arc / 2.0) / arc) * (w - 1)
    map_x = np.tile(src_x.astype(np.float32), (h, 1))

    # The cylinder axis is vertical, so a point's image height does not depend
    # on its angle around the cylinder: rows map straight through. Only the
    # horizontal axis compresses. (Adding vertical scaling here would bend
    # straight text lines into arcs, which is not what a bottle looks like.)
    map_y = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, out_w))

    curved = cv2.remap(
        arr, map_x, map_y, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )

    # Shade the edges: a real cylinder falls off in brightness as it turns away.
    shade = (0.55 + 0.45 * np.cos(theta)).astype(np.float32).reshape(1, -1, 1)
    curved = np.clip(curved.astype(np.float32) * shade, 0, 255).astype(np.uint8)

    pad = int(curved.shape[1] * 0.12)
    canvas = _counter_background(h + 2 * pad, curved.shape[1] + 2 * pad, seed=int(arc_deg))
    canvas[pad : pad + h, pad : pad + curved.shape[1]] = curved
    return Image.fromarray(canvas)


def add_glare(img: Image.Image, seed: int = 0, intensity: float = 0.85) -> Image.Image:
    """Add a specular highlight, as foil and laminate always do."""
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng = random.Random(seed)

    cx, cy = rng.uniform(0.25, 0.75) * w, rng.uniform(0.2, 0.6) * h
    rx, ry = rng.uniform(0.10, 0.22) * w, rng.uniform(0.05, 0.12) * h

    yy, xx = np.mgrid[0:h, 0:w]
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    glare = np.exp(-d * 1.6) * 255 * intensity
    arr = np.clip(arr + glare[..., None], 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def add_noise(img: Image.Image, sigma: float = 4.0, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = np.array(img).astype(np.float32)
    arr += rng.normal(0, sigma, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------------------
# Preset specs
# ---------------------------------------------------------------------------
def build_specs() -> list[tuple[str, PackSpec]]:
    """A spread from fully compliant to badly non-compliant."""
    return [
        ("compliant_biscuit", PackSpec(
            brand="Parle Products", product="Parle-G Glucose Biscuits",
            mrp=10.00, net_qty_value=250, net_qty_unit="g",
            mfg_date="03/2026", expiry_date="03/2027",
            manufacturer="Parle Products Pvt Ltd",
            address="Vile Parle East, Mumbai, Maharashtra - 400057",
            country="India", customer_care="1800-123-4567 | care@parle.example",
            fssai="10013022001234", barcode="8901234567890",
            pack_width_cm=12.0, pack_height_cm=18.0)),

        ("missing_unit_price", PackSpec(
            brand="Everest Spices", product="Everest Garam Masala",
            mrp=92.00, net_qty_value=100, net_qty_unit="g",
            mfg_date="01/2026", expiry_date="01/2027",
            manufacturer="Everest Food Products Pvt Ltd",
            address="Vashi, Navi Mumbai, Maharashtra - 400703",
            country="India", customer_care="1800-222-3333 | care@everest.example",
            fssai="10014033002345", barcode="8902345678901",
            pack_width_cm=9.0, pack_height_cm=14.0,
            omit={"unit_price"})),

        ("missing_mfg_and_origin", PackSpec(
            brand="Nutraj", product="Premium California Almonds",
            mrp=640.00, net_qty_value=500, net_qty_unit="g",
            mfg_date="12/2025", expiry_date="12/2026",
            manufacturer="Nutraj Foods Pvt Ltd",
            address="Sector 63, Noida, Uttar Pradesh - 201301",
            country="USA", customer_care="1800-444-5555 | hello@nutraj.example",
            fssai="10015044003456", barcode="8903456789012",
            pack_width_cm=14.0, pack_height_cm=20.0,
            omit={"mfg_date", "country_of_origin"})),

        ("undersized_font", PackSpec(
            brand="Local Foods Co", product="Mixed Fruit Jam",
            mrp=145.00, net_qty_value=500, net_qty_unit="g",
            mfg_date="02/2026", expiry_date="08/2026",
            manufacturer="Local Foods Company",
            address="Industrial Estate, Ludhiana, Punjab - 141003",
            country="India", customer_care="care@localfoods.example",
            fssai="10016055004567", barcode="8904567890123",
            pack_width_cm=10.0, pack_height_cm=15.0,
            undersize={"net_quantity", "mrp"})),

        ("expired_stock", PackSpec(
            brand="Mother Dairy", product="Fresh Paneer Block",
            mrp=95.00, net_qty_value=200, net_qty_unit="g",
            mfg_date="01/2025", expiry_date="15/02/2025",
            manufacturer="Mother Dairy Fruit & Vegetable Pvt Ltd",
            address="Patparganj, Delhi - 110092",
            country="India", customer_care="1800-180-1018",
            fssai="10017066005678", barcode="8905678901234",
            pack_width_cm=11.0, pack_height_cm=8.0)),

        ("curved_bottle", PackSpec(
            brand="Fortune", product="Sunlite Refined Sunflower Oil",
            mrp=145.00, net_qty_value=1, net_qty_unit="L",
            mfg_date="04/2026", expiry_date="04/2027",
            manufacturer="Adani Wilmar Limited",
            address="Ahmedabad, Gujarat - 380009",
            country="India", customer_care="1800-103-1023 | care@fortune.example",
            fssai="10018077006789", barcode="8906789012345",
            pack_width_cm=8.5, pack_height_cm=22.0,
            curved=True)),

        ("no_customer_care", PackSpec(
            brand="Balaji Wafers", product="Simply Salted Potato Wafers",
            mrp=20.00, net_qty_value=80, net_qty_unit="g",
            mfg_date="05/2026", expiry_date="09/2026",
            manufacturer="Balaji Wafers Pvt Ltd",
            address="Rajkot, Gujarat",
            country="India", customer_care="",
            fssai="10019088007890", barcode="8907890123456",
            pack_width_cm=13.0, pack_height_cm=17.0,
            omit={"customer_care"})),
    ]


def generate(
    spec: PackSpec, seed: int = 0, distort: bool = True
) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """Render a spec into a photograph-like image."""
    label, boxes = render_label(spec)
    if not distort:
        return label, boxes

    if spec.curved:
        img = apply_cylindrical(label, arc_deg=140.0)
    else:
        img, _corners = apply_perspective(label, strength=0.09, seed=seed)

    img = add_glare(img, seed=seed, intensity=0.7)
    img = add_noise(img, sigma=3.5, seed=seed)
    return img, boxes


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic packaging images")
    ap.add_argument("--out", default="../storage/uploads/demo", help="output directory")
    ap.add_argument("--clean", action="store_true", help="also write undistorted labels")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    for i, (name, spec) in enumerate(build_specs()):
        img, _boxes = generate(spec, seed=i, distort=True)
        path = out / f"{name}.jpg"
        img.save(path, quality=92)
        print(f"  {path.name:28} {img.size[0]}x{img.size[1]}  "
              f"{'curved' if spec.curved else 'planar'}"
              f"{'  omit=' + ','.join(sorted(spec.omit)) if spec.omit else ''}"
              f"{'  undersize=' + ','.join(sorted(spec.undersize)) if spec.undersize else ''}")
        if args.clean:
            clean, _ = generate(spec, seed=i, distort=False)
            clean.save(out / f"{name}_clean.png")

    print(f"\n  Wrote {len(build_specs())} synthetic packs to {out}")


if __name__ == "__main__":
    main()
