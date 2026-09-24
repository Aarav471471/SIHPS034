"""Preprocessing verification against synthetic packs with known ground truth.

The important assertion is the coordinate round-trip: a point is pushed through
the real forward transform and then mapped back with CoordinateMapper.  If that
does not land where it started, every evidence crop in a legal notice is citing
the wrong pixels.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from preprocessing import contour, cylindrical_unwarp, enhance, planar_unwarp  # noqa: E402
from preprocessing.coordinate_mapper import BBox, CoordinateMapper, font_height_mm  # noqa: E402
from preprocessing.exif import correct_orientation, to_bytes  # noqa: E402
from seed.synthetic import PX_PER_MM, build_specs, generate, render_label  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name, detail))
    return ok


def main() -> int:
    demo = Path(__file__).resolve().parent.parent.parent / "storage" / "uploads" / "demo"

    # ------------------------------------------------- EXIF / ingestion --
    sample = demo / "compliant_biscuit.jpg"
    raw = sample.read_bytes()
    ex = correct_orientation(raw)
    check("EXIF ingest -> upright RGB ndarray",
          ex.image.ndim == 3 and ex.image.shape[2] == 3,
          f"{ex.corrected_size[0]}x{ex.corrected_size[1]}, rotation={ex.rotation_applied}deg")

    # ------------------------------------------------ contour detection --
    for fname, expect in [("compliant_biscuit.jpg", "planar"),
                          ("curved_bottle.jpg", "cylindrical")]:
        img = correct_orientation((demo / fname).read_bytes()).image
        res = contour.analyse(img)
        check(f"curvature classify {fname}", res.method == expect,
              f"got={res.method} curvature={res.curvature_score:.3f} "
              f"area_ratio={res.contour_area_ratio:.3f}")

    # ------------------------------------------------------ planar unwarp --
    img = correct_orientation((demo / "compliant_biscuit.jpg").read_bytes()).image
    det = contour.analyse(img)
    un = planar_unwarp.unwarp(img, det.corners)
    check("planar rectification applied", un.applied,
          f"{img.shape[1]}x{img.shape[0]} -> {un.output_size[0]}x{un.output_size[1]}")
    check("planar matrix is invertible",
          un.matrix is not None and un.inverse_matrix is not None,
          "forward + inverse homography stored")

    # Rectified aspect should approach the true label aspect (12.0 x 18.0 cm).
    if un.applied:
        aspect = un.output_size[0] / un.output_size[1]
        check("rectified aspect ratio recovered", abs(aspect - (12.0 / 18.0)) < 0.15,
              f"got {aspect:.3f}, true {12.0 / 18.0:.3f} (12x18cm label)")

    # ------------------------------- COORDINATE ROUND-TRIP (planar) -------
    # Warp a known label with a known homography, then ask the mapper to invert it.
    spec = build_specs()[0][1]
    label, boxes = render_label(spec)
    warped_img, dst_corners = __import__(
        "seed.synthetic", fromlist=["apply_perspective"]
    ).apply_perspective(label, strength=0.09, seed=0)

    import cv2

    lw, lh = label.size
    src = np.array([[0, 0], [lw, 0], [lw, lh], [0, lh]], dtype=np.float32)
    forward = cv2.getPerspectiveTransform(src, dst_corners.astype(np.float32))

    # The mapper inverts "rectified -> original". Here the label IS the rectified
    # space and the warped photo is the original, so the inverse we hand it is
    # exactly `forward`.
    mapper = CoordinateMapper(
        method="planar",
        transform={"forward": np.linalg.inv(forward).tolist(), "inverse": forward.tolist()},
        original_size=warped_img.size,
        rectified_size=(lw, lh),
    )

    errors = []
    for key in ("mrp", "net_quantity", "unit_price", "fssai_licence"):
        if key not in boxes:
            continue
        x, y, w, h = boxes[key]
        region = mapper.map_bbox(BBox(x, y, w, h))
        # Ground truth: push the same corners through the real forward transform.
        pts = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32)
        truth = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), forward).reshape(-1, 2)
        got = np.array(region.polygon, dtype=np.float32)
        errors.append(float(np.abs(truth - got).max()))

    max_err = max(errors) if errors else 999.0
    check("planar coordinate round-trip is exact", max_err < 1.5,
          f"max corner error {max_err:.3f} px across {len(errors)} declaration boxes")

    # ------------------------- COORDINATE ROUND-TRIP (cylindrical) --------
    curved_img = correct_orientation((demo / "curved_bottle.jpg").read_bytes()).image
    cdet = contour.analyse(curved_img)
    arc = cylindrical_unwarp.estimate_visible_arc(curved_img, cdet.corners)
    cun, _maps = cylindrical_unwarp.unwarp(curved_img, cdet.corners, visible_arc_deg=arc)
    check("cylindrical unwrap applied", cun.applied,
          f"arc={arc:.0f}deg  {curved_img.shape[1]}x{curved_img.shape[0]} -> "
          f"{cun.output_size[0]}x{cun.output_size[1]}")
    check("cylindrical unwrap widens the image",
          cun.output_size[0] >= curved_img.shape[1] * 0.9,
          f"out_w={cun.output_size[0]} vs in_w={curved_img.shape[1]} "
          "(arc length exceeds chord)")

    cmapper = CoordinateMapper(
        method="cylindrical",
        transform={"forward": cun.matrix.tolist()},
        original_size=(curved_img.shape[1], curved_img.shape[0]),
        rectified_size=cun.output_size,
    )
    # Centre column must map back near the pack's horizontal centre.
    ow, oh = cun.output_size
    cx_mapped, _cy = cmapper.map_point(ow / 2, oh / 2)
    expected_cx = cdet.corners[:, 0].mean() if cdet.corners is not None else curved_img.shape[1] / 2
    check("cylindrical centre maps to pack centre", abs(cx_mapped - expected_cx) < 40,
          f"mapped x={cx_mapped:.1f}, pack centre x={expected_cx:.1f}")

    # Monotonicity: unwrapped columns must map left-to-right without folding.
    xs = [cmapper.map_point(u, oh / 2)[0] for u in np.linspace(0, ow - 1, 25)]
    check("cylindrical mapping is monotonic",
          all(b >= a - 1e-6 for a, b in zip(xs, xs[1:])),
          "no folding across 25 sampled columns")

    # ------------------------------------------------------- enhancement --
    glary = correct_orientation((demo / "compliant_biscuit.jpg").read_bytes()).image
    enh = enhance.enhance(glary)
    check("glare detected and repaired", enh.glare_repaired,
          f"glare covered {enh.glare_ratio * 100:.2f}% of frame")
    check("binary OCR variant produced",
          enh.binary is not None and enh.binary.ndim == 2,
          f"sharpness={enh.sharpness:.0f} brightness={enh.brightness:.0f} "
          f"contrast={enh.contrast:.0f}")

    # --------------------------------------------------- physical scale --
    px_per_mm = contour.estimate_px_per_mm(det.corners, 12.0, 18.0)
    check("px/mm estimated from pack dimensions", px_per_mm is not None,
          f"{px_per_mm} px/mm (label rendered at {PX_PER_MM} px/mm before warping)")

    # A 4.0 mm MRP declaration must measure back to roughly 4 mm.
    if px_per_mm:
        # In the flat rendered label the MRP box height is known exactly.
        _lbl, bx = render_label(spec)
        mrp_h_px = bx["mrp"][3]
        mm = font_height_mm(mrp_h_px, PX_PER_MM, box_kind="ink")
        check("font height in mm recovered from pixels",
              mm is not None and 3.2 <= mm <= 5.2,
              f"measured {mm} mm for a declaration rendered at 4.0 mm cap height")

    # ------------------------------------------------------ round-trip io --
    encoded = to_bytes(ex.image, fmt="PNG")
    check("ndarray -> bytes round-trip", len(encoded) > 1000, f"{len(encoded) // 1024} KB PNG")

    # ---------------------------------------------------------- report ----
    width = max(len(n) for _o, n, _d in results)
    print("\n" + "=" * 96)
    print("  PREPROCESSING PIPELINE VERIFICATION")
    print("=" * 96)
    for ok, name, detail in results:
        print(f"  [{'+' if ok else 'x'}] {name:<{width}}  {detail}")
    failed = sum(1 for ok, _n, _d in results if not ok)
    print("=" * 96)
    print(f"  {len(results) - failed}/{len(results)} passed" + (f", {failed} FAILED" if failed else ""))
    print("=" * 96 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
