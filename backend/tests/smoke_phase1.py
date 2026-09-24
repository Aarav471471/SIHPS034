"""Phase 1 end-to-end: the officer workflow over the real HTTP API.

Opens a session, uploads a real synthetic pack, runs the six-stage pipeline,
and checks that the persisted findings, evidence crops and tamper seal are all
consistent -- the chain a legal notice would actually rest on.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.main import app  # noqa: E402
from seed.seed import DEMO_PASSWORD  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent.parent / "storage" / "uploads" / "demo"
results: list[tuple[bool, str, str]] = []


def fresh_capture(name: str) -> bytes:
    """Load a demo pack as a byte-unique capture.

    Evidence hashes are globally UNIQUE by design -- the same photograph can
    never enter evidence twice, in any session. That is correct enforcement
    behaviour but makes a fixed test image usable exactly once, so each run
    re-encodes with imperceptible per-run noise. Two real photographs of the
    same pack are never byte-identical either.
    """
    import io
    import secrets

    import numpy as np
    from PIL import Image

    with Image.open(DEMO / name) as img:
        arr = np.array(img.convert("RGB")).astype(np.int16)

    rng = np.random.default_rng(secrets.randbits(32))
    # +/-1 on a handful of pixels: changes the hash, changes nothing visible.
    ys = rng.integers(0, arr.shape[0], 64)
    xs = rng.integers(0, arr.shape[1], 64)
    arr[ys, xs] = np.clip(arr[ys, xs] + rng.choice([-1, 1], (64, 3)), 0, 255)

    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name, detail))
    return ok


async def main() -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=600) as c:
        # ---------------------------------------------------------- login --
        r = await c.post("/api/auth/login",
                         json={"username": "officer.sharma", "password": DEMO_PASSWORD})
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        check("officer login", r.status_code == 200, r.json()["user"]["jurisdiction_name"])

        # -------------------------------------------------- create session --
        r = await c.post("/api/inspections/session", headers=auth, json={
            "product_name": "Parle-G Glucose Biscuits",
            "brand_name": "Parle Products",
            "product_category": "Biscuits & Cookies",
            "package_width_cm": 12.0,
            "package_height_cm": 18.0,
            "latitude": 28.6519, "longitude": 77.1909,   # Karol Bagh, in-zone
            "store_name": "Sharma Supermart",
        })
        created = r.status_code == 201
        sid = r.json()["session_id"] if created else None
        check("create inspection session", created,
              f"{sid} jurisdiction={r.json().get('jurisdiction_status') if created else r.status_code}")
        check("geofence stamped WITHIN_BOUNDS",
              created and r.json().get("jurisdiction_status") == "WITHIN_BOUNDS",
              "Karol Bagh falls inside Delhi Central Zone")

        # Out-of-jurisdiction capture must be flagged, not rejected.
        r2 = await c.post("/api/inspections/session", headers=auth, json={
            "product_name": "Test", "latitude": 28.4692, "longitude": 77.0322,  # Gurugram
            "store_name": "Gurgaon Value Store",
        })
        check("out-of-zone capture flagged OUT_OF_BOUNDS",
              r2.json().get("jurisdiction_status") == "OUT_OF_BOUNDS",
              "recorded for review rather than refused")

        # -------------------------------------------------- upload surface --
        img = fresh_capture("compliant_biscuit.jpg")
        r = await c.post(
            f"/api/inspections/{sid}/images", headers=auth,
            files={"file": ("front.jpg", img, "image/jpeg")},
            data={"surface_type": "FRONT"},
        )
        up = r.status_code == 201
        check("upload FRONT surface", up,
              f"{r.json().get('width_px')}x{r.json().get('height_px')} "
              f"sha256={r.json().get('sha256_hash', '')[:16]}..." if up else str(r.status_code))

        # The same bytes must be refused -- SHA-256 is UNIQUE in the schema.
        r = await c.post(
            f"/api/inspections/{sid}/images", headers=auth,
            files={"file": ("again.jpg", img, "image/jpeg")},
            data={"surface_type": "BACK"},
        )
        check("duplicate image rejected by evidence hash", r.status_code == 409,
              f"got {r.status_code}")

        # A genuinely different surface is accepted.
        back = fresh_capture("missing_unit_price.jpg")
        r = await c.post(
            f"/api/inspections/{sid}/images", headers=auth,
            files={"file": ("back.jpg", back, "image/jpeg")},
            data={"surface_type": "BACK"},
        )
        check("upload BACK surface", r.status_code == 201, "distinct hash accepted")

        # ------------------------------------------------------- pipeline --
        r = await c.post(f"/api/inspections/{sid}/process", headers=auth)
        queued = r.status_code == 200
        check("pipeline queued", queued,
              r.json().get("message", "")[:70] if queued else str(r.status_code))

        # Poll for completion (the dev runner executes in a thread pool).
        final = None
        for _ in range(120):
            await asyncio.sleep(1)
            r = await c.get(f"/api/inspections/{sid}", headers=auth)
            if r.json()["status"] not in ("PENDING", "PROCESSING"):
                final = r.json()
                break

        if final is None:
            check("pipeline completed", False, "timed out after 120s")
        else:
            check("pipeline completed", True,
                  f"status={final['status']} score={final['overall_score']} "
                  f"compliance={final['compliance_status']} "
                  f"confidence={final['confidence_score']}")

            check("declarations extracted", len(final["fields"]) >= 6,
                  f"{len(final['fields'])} fields: "
                  + ", ".join(sorted(f['field_name'] for f in final['fields'])[:6]))

            check("findings recorded with legal clauses",
                  all(v.get("legal_clause") for v in final["violations"]),
                  f"{len(final['violations'])} findings, each citing a clause")

            crops = [f for f in final["fields"] if f.get("crop_url")]
            check("evidence crops stored for cited declarations", len(crops) > 0,
                  f"{len(crops)} pixel crops written to storage")

            check("bounding boxes mapped to original pixels",
                  any(f.get("bbox_x") is not None for f in final["fields"]),
                  "coordinates cite the officer's untouched photograph")

            surfaces = {i["surface_type"] for i in final["images"]}
            check("multi-surface inspection", surfaces == {"FRONT", "BACK"},
                  f"surfaces={sorted(surfaces)}, "
                  f"unwarp={[i.get('unwarp_method') for i in final['images']]}")

        # -------------------------------------------------- evidence seal --
        r = await c.get(f"/api/inspections/{sid}/evidence-seal", headers=auth)
        seal = r.json()
        check("evidence seal verifies", seal.get("intact") is True,
              f"{seal.get('image_count')} images chained, seal={str(seal.get('seal'))[:16]}...")

        # ------------------------------------------------------ escalation --
        r = await c.post(f"/api/inspections/{sid}/escalate", headers=auth,
                         json={"reason": "Unit price arithmetic contested by the retailer"})
        # The pipeline escalates automatically under spec 3.E when confidence
        # lands in the review band, so a second manual referral on the same
        # session is correctly refused as a duplicate. Either outcome proves the
        # escalation path works; a 409 additionally proves the auto-trigger fired.
        auto = final is not None and final["status"] == "PEER_REVIEW"
        check("escalation to senior peer review",
              r.status_code == 200 or (r.status_code == 409 and auto),
              "auto-escalated by the pipeline; duplicate referral refused"
              if r.status_code == 409 else r.json().get("detail", ""))

        # An officer must not be able to decide their own escalation.
        r = await c.post(f"/api/inspections/{sid}/peer-review", headers=auth,
                         json={"decision": "APPROVED", "remarks": "Self-approval attempt"})
        check("officer cannot decide their own peer review", r.status_code == 403,
              f"got {r.status_code}")

        # A senior officer can.
        r = await c.post("/api/auth/login",
                         json={"username": "senior.iyer", "password": DEMO_PASSWORD})
        senior = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = await c.post(f"/api/inspections/{sid}/peer-review", headers=senior,
                         json={"decision": "APPROVED",
                               "remarks": "Pixel crops reviewed; findings sustained."})
        check("senior officer decides peer review", r.status_code == 200,
              r.json().get("detail", ""))

        # ------------------------------------------------- locked evidence --
        r = await c.post(
            f"/api/inspections/{sid}/images", headers=auth,
            files={"file": ("late.jpg", fresh_capture("expired_stock.jpg"), "image/jpeg")},
            data={"surface_type": "SIDE"},
        )
        check("locked session refuses new evidence", r.status_code == 409,
              "evidence set is immutable once a notice is approved")

        # ------------------------------------------------------- listing ---
        r = await c.get("/api/inspections?page=1&page_size=5", headers=auth)
        check("session listing paginates", r.status_code == 200,
              f"{r.json()['total']} total sessions for this officer")

        # --------------------------------------------------- capabilities --
        r = await c.get("/health/capabilities")
        caps = r.json()
        check("runtime capabilities reported", r.status_code == 200,
              f"vision={caps['vision']['provider']} ocr_rapid={caps['ocr']['rapidocr']} "
              f"opencv={caps['computer_vision']['opencv']}")

    width = max(len(n) for _o, n, _d in results)
    print("\n" + "=" * 110)
    print("  PHASE 1 END-TO-END: OFFICER INSPECTION WORKFLOW")
    print("=" * 110)
    for ok, name, detail in results:
        print(f"  [{'+' if ok else 'x'}] {name:<{width}}  {detail}")
    failed = sum(1 for ok, _n, _d in results if not ok)
    print("=" * 110)
    print(f"  {len(results) - failed}/{len(results)} passed" + (f", {failed} FAILED" if failed else ""))
    print("=" * 110 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
