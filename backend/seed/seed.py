"""Demo corpus builder.

Produces a database where every screen of every portal has something real to
show: historical inspections with violations, a price-gouging cluster the radar
will actually flag, citizen leads at varying trust levels, escalated cases
waiting in the senior queue, brand disputes mid-appeal, and cross-agency records
with genuinely lapsed licences.

Deterministic by construction (fixed RNG seed) so a demo replays identically.

Usage:
    python -m seed.seed            # create if empty
    python -m seed.seed --reset    # drop everything and rebuild
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, drop_db, init_db  # noqa: E402
from core.security import generate_token, hash_password, seal_evidence, sha256_bytes  # noqa: E402
from models import (  # noqa: E402
    BrandDispute,
    BrandPreCert,
    Category,
    CitizenReport,
    ConsumerAlert,
    CrossAgencyLink,
    EcomListingCrosscheck,
    ExtractedField,
    InspectionSession,
    PeerReview,
    PriceHistoryScan,
    Product,
    SessionImage,
    User,
    Violation,
)
from models.enums import (  # noqa: E402
    AlertType,
    AppellateStatus,
    ComplianceStatus,
    EcomPlatform,
    JurisdictionStatus,
    PeerReviewStatus,
    PeerReviewTrigger,
    ReportCategory,
    ReportStatus,
    SessionStatus,
    SourceType,
    SurfaceType,
    UserRole,
    badge_for_score,
)
from seed.data import (  # noqa: E402
    CATEGORIES,
    JURISDICTIONS,
    LEGAL_CLAUSES,
    PENALTY_BANDS,
    PRODUCTS,
    STORES,
    make_ean13,
)

RNG = random.Random(26034)  # SIH problem statement number, for luck
NOW = datetime.now(timezone.utc)

DEMO_PASSWORD = "Metrix@2026"


def ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


# ===========================================================================
# Users
# ===========================================================================
OFFICERS = [
    ("officer.sharma", "Rajesh Sharma", "LM-DL-1042", "Delhi Central Zone", UserRole.OFFICER),
    ("officer.verma", "Anita Verma", "LM-DL-1088", "Delhi South Zone", UserRole.OFFICER),
    ("officer.khan", "Imran Khan", "LM-DL-1123", "Delhi West Zone", UserRole.OFFICER),
    ("officer.reddy", "Sunitha Reddy", "LM-UP-2051", "Gautam Buddh Nagar (Noida)", UserRole.OFFICER),
    ("senior.iyer", "Lakshmi Iyer", "LM-DL-0012", "Delhi Central Zone", UserRole.SENIOR_OFFICER),
    ("senior.chauhan", "Vikram Chauhan", "LM-DL-0031", "Delhi North Zone", UserRole.SENIOR_OFFICER),
]

CONSUMERS = [
    ("citizen.priya", "Priya Nair", 92.0, True),
    ("citizen.arjun", "Arjun Mehta", 84.0, True),
    ("citizen.fatima", "Fatima Sheikh", 70.0, False),
    ("citizen.rohit", "Rohit Kulkarni", 60.0, False),
    ("citizen.deepa", "Deepa Rangan", 50.0, False),
    ("citizen.sameer", "Sameer Joshi", 50.0, False),
    ("citizen.ananya", "Ananya Das", 30.0, False),
    ("citizen.manish", "Manish Gupta", 88.0, True),
]

BRANDS = [
    ("brand.parle", "Parle Products", "compliance@parleproducts.example"),
    ("brand.britannia", "Britannia Industries", "labels@britannia.example"),
    ("brand.fortune", "Adani Wilmar", "regulatory@adaniwilmar.example"),
    ("brand.mdh", "MDH", "quality@mdhspices.example"),
    ("brand.haldiram", "Haldiram's", "packaging@haldirams.example"),
]


async def seed_users(db: AsyncSession) -> dict[str, User]:
    users: dict[str, User] = {}

    admin = User(
        username="admin",
        email="admin@metrix.gov.in",
        hashed_password=hash_password(DEMO_PASSWORD),
        role=UserRole.ADMIN,
        full_name="Platform Administrator",
        department="Ministry of Consumer Affairs",
        officer_id="LM-ADMIN-0001",
        is_active=True,
    )
    db.add(admin)
    users["admin"] = admin

    for username, name, oid, zone, role in OFFICERS:
        u = User(
            username=username,
            email=f"{username}@lm.gov.in",
            hashed_password=hash_password(DEMO_PASSWORD),
            role=role,
            full_name=name,
            officer_id=oid,
            department="Legal Metrology Department",
            jurisdiction_name=zone,
            jurisdiction_geojson=JURISDICTIONS[zone],
            phone=f"+9198{RNG.randint(10000000, 99999999)}",
        )
        db.add(u)
        users[username] = u

    for username, name, trust, verified in CONSUMERS:
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password(DEMO_PASSWORD),
            role=UserRole.CONSUMER,
            full_name=name,
            citizen_trust_score=trust,
            verified_reporter=verified,
            phone=f"+9197{RNG.randint(10000000, 99999999)}",
        )
        db.add(u)
        users[username] = u

    for username, brand, email in BRANDS:
        u = User(
            username=username,
            email=email,
            hashed_password=hash_password(DEMO_PASSWORD),
            role=UserRole.BRAND,
            full_name=f"{brand} Compliance Desk",
            brand_name=brand,
        )
        db.add(u)
        users[username] = u

    await db.flush()
    for username, _b, _e in BRANDS:
        users[username].brand_id = users[username].id
    await db.flush()
    return users


# ===========================================================================
# Catalogue
# ===========================================================================
async def seed_catalogue(db: AsyncSession) -> tuple[dict[str, Category], list[Product]]:
    cats: dict[str, Category] = {}
    for c in CATEGORIES:
        cat = Category(**c)
        db.add(cat)
        cats[c["slug"]] = cat
    await db.flush()

    products: list[Product] = []
    for i, (slug, brand, name, mrp, qty, unit, origin) in enumerate(PRODUCTS, start=1):
        # Compliance profile: most products are healthy, a deliberate tail is not.
        roll = RNG.random()
        if roll < 0.55:
            score = RNG.uniform(90, 99)
        elif roll < 0.80:
            score = RNG.uniform(78, 90)
        elif roll < 0.93:
            score = RNG.uniform(60, 78)
        else:
            score = RNG.uniform(35, 60)

        p = Product(
            category_id=cats[slug].id,
            brand_name=brand,
            product_name=name,
            barcode=make_ean13(i),
            official_mrp=mrp,
            net_quantity=f"{qty:g} {unit}",
            net_quantity_value=float(qty),
            net_quantity_unit=unit,
            country_of_origin=origin,
            fssai_number=f"1{RNG.randint(1000000000000, 9999999999999)}"[:14]
            if cats[slug].sector in ("Food", "Healthcare")
            else None,
            avg_score=round(score, 1),
            badge_level=badge_for_score(score),
            total_inspections=RNG.randint(1, 24),
            violation_count=0 if score > 88 else RNG.randint(1, 6),
            last_inspected_at=ago(days=RNG.uniform(1, 120)),
        )
        db.add(p)
        products.append(p)
    await db.flush()

    # Roll product scores up into category averages
    for slug, cat in cats.items():
        members = [p for p in products if p.category_id == cat.id]
        if members:
            cat.total_inspections = sum(p.total_inspections for p in members)
            cat.avg_compliance_score = round(
                sum(p.avg_score or 0 for p in members) / len(members), 1
            )
    await db.flush()
    return cats, products


# ===========================================================================
# Inspection history (sessions + images + fields + violations)
# ===========================================================================
FIELD_SPECS = [
    ("mrp", "MRP", SurfaceType.FRONT),
    ("net_quantity", "Net Quantity", SurfaceType.FRONT),
    ("unit_price", "Unit Sale Price", SurfaceType.FRONT),
    ("manufacturer_name", "Manufacturer", SurfaceType.BACK),
    ("manufacturer_address", "Manufacturer Address", SurfaceType.BACK),
    ("mfg_date", "Month & Year of Manufacture", SurfaceType.BACK),
    ("expiry_date", "Best Before", SurfaceType.BACK),
    ("country_of_origin", "Country of Origin", SurfaceType.BACK),
    ("customer_care", "Consumer Care", SurfaceType.BACK),
    ("fssai_licence", "FSSAI Licence", SurfaceType.BACK),
]

VIOLATION_TEMPLATES = [
    ("R-UNIT-PRICE", "Unit Sale Price Missing", "unit_price", "unit_price",
     "No unit sale price declared on the principal display panel.", "MAJOR"),
    ("R-FONT-HEIGHT", "Declaration Font Below Minimum Height", "net_quantity", "font_height",
     "Net quantity numerals measure below the minimum height for this pack size.", "MINOR"),
    ("R-MFG-DATE", "Manufacture Date Not Declared", "mfg_date", "mfg_date",
     "Month and year of manufacture absent from all captured surfaces.", "MAJOR"),
    ("R-COUNTRY-ORIGIN", "Country of Origin Missing", "country_of_origin", "country_of_origin",
     "Country of origin not declared on an imported commodity.", "MAJOR"),
    ("R-CUSTOMER-CARE", "Consumer Care Details Incomplete", "customer_care", "customer_care",
     "No consumer care telephone or email address printed on the pack.", "MINOR"),
    ("R-MRP-FORMAT", "MRP Not Declared as Inclusive of Taxes", "mrp", "mrp_inclusive",
     "Retail sale price printed without the mandatory inclusive-of-all-taxes wording.", "MAJOR"),
    ("R-PINCODE", "Manufacturer Address Missing PIN Code", "manufacturer_address", "pincode",
     "Manufacturer address printed without a six-digit PIN code.", "MINOR"),
    ("R-EXPIRED-STOCK", "Expired Commodity Offered for Sale", "expiry_date", "expired_stock",
     "Best-before date has elapsed while the commodity remains on shelf.", "CRITICAL"),
    ("R-FSSAI", "FSSAI Licence Number Invalid", "fssai_licence", "fssai_licence",
     "Declared FSSAI licence number fails the 14-digit format check.", "MAJOR"),
]


async def seed_inspections(
    db: AsyncSession, users: dict[str, User], products: list[Product]
) -> list[InspectionSession]:
    officers = [users[o[0]] for o in OFFICERS]
    sessions: list[InspectionSession] = []

    for n in range(1, 141):
        officer = RNG.choice(officers)
        product = RNG.choice(products)
        store = RNG.choice(STORES)
        created = ago(days=RNG.uniform(0.2, 150))

        # Sessions mostly reflect their product's compliance profile.
        base = product.avg_score or 85
        score = int(max(20, min(100, RNG.gauss(base, 9))))

        n_violations = 0 if score >= 92 else (1 if score >= 80 else RNG.randint(2, 4))
        picked = RNG.sample(VIOLATION_TEMPLATES, k=min(n_violations, len(VIOLATION_TEMPLATES)))

        confidence = round(RNG.uniform(0.55, 0.99), 3)
        penalty = sum(PENALTY_BANDS.get(v[3], 10_000) for v in picked)

        # Escalation rules from spec 3.E
        needs_review = (
            settings.CONFIDENCE_REVIEW_FLOOR <= confidence < settings.CONFIDENCE_ACCEPT_THRESHOLD
            or penalty > settings.PEER_REVIEW_PENALTY_THRESHOLD
        )
        if picked and needs_review and RNG.random() < 0.7:
            status = SessionStatus.PEER_REVIEW
        elif picked:
            status = SessionStatus.FLAGGED if RNG.random() < 0.35 else SessionStatus.COMPLETED
        else:
            status = SessionStatus.COMPLETED

        width = round(RNG.uniform(6, 22), 1)
        height = round(RNG.uniform(9, 30), 1)

        s = InspectionSession(
            session_id=f"sess_{n:05d}",
            officer_id=officer.id,
            source_type=SourceType.OFFICER,
            status=status,
            overall_score=score,
            compliance_status=(
                ComplianceStatus.COMPLIANT
                if not picked
                else (
                    ComplianceStatus.NON_COMPLIANT
                    if any(v[5] in ("MAJOR", "CRITICAL") for v in picked)
                    else ComplianceStatus.WARNING
                )
            ),
            confidence_score=confidence,
            estimated_penalty=penalty if picked else None,
            package_width_cm=width,
            package_height_cm=height,
            surface_area_cm2=round(width * height, 2),
            product_category=product.category.name if product.category else None,
            category_id=product.category_id,
            product_id=product.id,
            brand_name=product.brand_name,
            product_name=product.product_name,
            barcode=product.barcode,
            barcode_verified=RNG.random() < 0.88,
            latitude=store["lat"] + RNG.uniform(-0.002, 0.002),
            longitude=store["lng"] + RNG.uniform(-0.002, 0.002),
            store_name=store["name"],
            location_address=store["address"],
            jurisdiction_status=(
                JurisdictionStatus.WITHIN_BOUNDS
                if RNG.random() < 0.94
                else JurisdictionStatus.OUT_OF_BOUNDS
            ),
            is_locked=status in (SessionStatus.COMPLETED, SessionStatus.RESOLVED),
            created_at=created,
            completed_at=created + timedelta(minutes=RNG.uniform(1, 6)),
        )
        db.add(s)
        await db.flush()

        # --- surfaces ---
        hashes = []
        for surface in (SurfaceType.FRONT, SurfaceType.BACK):
            raw = f"{s.session_id}:{surface}:{n}".encode()
            digest = sha256_bytes(raw)
            hashes.append(digest)
            curved = RNG.random() < 0.25
            db.add(
                SessionImage(
                    session_id=s.id,
                    surface_type=surface,
                    image_path=f"uploads/demo/{s.session_id}_{surface}.jpg",
                    sha256_hash=digest,
                    perceptual_hash=f"{RNG.getrandbits(64):016x}",
                    image_width_px=RNG.choice([1440, 1920, 2160]),
                    image_height_px=RNG.choice([1920, 2560, 3840]),
                    file_size_bytes=RNG.randint(400_000, 3_500_000),
                    is_curved_surface=curved,
                    curvature_score=round(RNG.uniform(0.3, 0.9), 3) if curved else round(RNG.uniform(0, 0.2), 3),
                    unwarp_method="cylindrical" if curved else "planar",
                    px_per_mm=round(RNG.uniform(7.5, 14.0), 2),
                    uploaded_at=created,
                )
            )
        s.evidence_seal = seal_evidence(s.session_id, hashes)

        # --- extracted fields ---
        missing_fields = {v[2] for v in picked}
        for fname, _label, surface in FIELD_SPECS:
            is_missing = fname in missing_fields and RNG.random() < 0.8
            v_conf = round(RNG.uniform(0.72, 0.99), 3)
            o_conf = round(min(0.99, max(0.4, v_conf + RNG.uniform(-0.15, 0.06))), 3)
            value = None
            if not is_missing:
                value = {
                    "mrp": f"Rs. {product.official_mrp:.2f} (Incl. of all taxes)",
                    "net_quantity": product.net_quantity,
                    "unit_price": product.unit_price_display,
                    "manufacturer_name": product.brand_name,
                    "manufacturer_address": "Plot 4, Industrial Area, Delhi - 110020",
                    "mfg_date": (created - timedelta(days=RNG.randint(30, 300))).strftime("%m/%Y"),
                    "expiry_date": (created + timedelta(days=RNG.randint(-20, 400))).strftime("%d/%m/%Y"),
                    "country_of_origin": product.country_of_origin,
                    "customer_care": "1800-000-000 | care@example.com",
                    "fssai_licence": product.fssai_number,
                }.get(fname)

            db.add(
                ExtractedField(
                    session_id=s.id,
                    field_name=fname,
                    detected_value=value,
                    normalized_value=value,
                    surface_found=None if is_missing else surface,
                    bbox_x=RNG.randint(40, 900) if not is_missing else None,
                    bbox_y=RNG.randint(40, 1400) if not is_missing else None,
                    bbox_width=RNG.randint(80, 480) if not is_missing else None,
                    bbox_height=RNG.randint(22, 70) if not is_missing else None,
                    confidence_vision_llm=None if is_missing else v_conf,
                    confidence_ocr_verify=None if is_missing else o_conf,
                    ocr_agreement=None if is_missing else (abs(v_conf - o_conf) < 0.12),
                    ocr_read_value=value,
                    raw_pixel_crop_path=None if is_missing else f"crops/demo/{s.session_id}_{fname}.png",
                    font_height_mm=round(RNG.uniform(1.2, 4.5), 2) if not is_missing else None,
                    is_missing=is_missing,
                    created_at=created,
                )
            )

        # --- violations ---
        for rule_id, rule_name, field_name, clause_key, evidence, severity in picked:
            db.add(
                Violation(
                    session_id=s.id,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    field_name=field_name,
                    status="FAIL" if severity in ("MAJOR", "CRITICAL") else "WARNING",
                    evidence_text=evidence,
                    legal_clause=LEGAL_CLAUSES.get(clause_key, ""),
                    severity=severity,
                    confidence=round(RNG.uniform(0.65, 0.98), 3),
                    evidence_crop_path=f"crops/demo/{s.session_id}_{field_name}.png",
                    penalty_amount=PENALTY_BANDS.get(clause_key, 10_000.0),
                    created_at=created,
                )
            )

        sessions.append(s)

    await db.flush()
    return sessions


# ===========================================================================
# Price-Gouging Radar corpus
# ===========================================================================
async def seed_price_history(
    db: AsyncSession, users: dict[str, User], products: list[Product]
) -> None:
    """Build a scan history with a deliberate tampering cluster.

    Three stores are made repeat offenders on popular SKUs so the radar has a
    genuine, reproducible anomaly to surface during a demo rather than needing
    luck.
    """
    consumers = [users[c[0]] for c in CONSUMERS]
    officers = [users[o[0]] for o in OFFICERS]
    gouging_stores = {"Gupta General Store", "Agarwal Kirana Store", "Krishna Provision Mart"}

    popular = [p for p in products if (p.official_mrp or 0) <= 120][:40]

    for product in popular:
        base = product.official_mrp or 50.0
        for _ in range(RNG.randint(6, 18)):
            store = RNG.choice(STORES)
            is_gouger = store["name"] in gouging_stores and RNG.random() < 0.55

            if is_gouger:
                factor = RNG.uniform(1.10, 1.60)  # clearly above the 1.05 threshold
            else:
                factor = RNG.uniform(0.995, 1.005)  # honest retailers print the MRP

            scanned = round(base * factor, 2)
            overcharge = ((scanned - base) / base) * 100 if base else 0.0
            anomalous = factor > settings.RADAR_TAMPER_MULTIPLIER

            from_officer = RNG.random() < 0.2
            scanner = RNG.choice(officers if from_officer else consumers)

            db.add(
                PriceHistoryScan(
                    barcode=product.barcode,
                    product_name=product.product_name,
                    brand_name=product.brand_name,
                    scanned_mrp=scanned,
                    modal_mrp_at_scan=base,
                    scanned_by_user_id=scanner.id,
                    source="OFFICER" if from_officer else "CONSUMER",
                    store_name=store["name"],
                    latitude=store["lat"] + RNG.uniform(-0.001, 0.001),
                    longitude=store["lng"] + RNG.uniform(-0.001, 0.001),
                    is_anomalous=anomalous,
                    anomaly_reason=(
                        f"Printed MRP Rs.{scanned:.2f} exceeds modal MRP Rs.{base:.2f} "
                        f"by {overcharge:.1f}% at this retailer"
                    )
                    if anomalous
                    else None,
                    overcharge_pct=round(overcharge, 2) if anomalous else None,
                    scanned_at=ago(days=RNG.uniform(0, settings.RADAR_WINDOW_DAYS)),
                )
            )
    await db.flush()


# ===========================================================================
# Citizen reports, peer reviews, brand workflows, e-com, agency graph, alerts
# ===========================================================================
REPORT_REMARKS = [
    ("Selling Rs.10 pack for Rs.15 by putting black marker over the printed MRP", ReportCategory.OVERCHARGING),
    ("Expiry date completely missing from the back panel of this pack", ReportCategory.MISSING_EXPIRY),
    ("Shopkeeper is stocking packets that expired last month", ReportCategory.EXPIRED_STOCK),
    ("Net weight is not printed anywhere on the packet", ReportCategory.MISSING_NET_QTY),
    ("New MRP sticker pasted on top of the original printed price", ReportCategory.OVERCHARGING),
    ("MRP label scratched off deliberately at the counter", ReportCategory.MISSING_MRP),
    ("Charged Rs.25 for a bottle clearly marked Rs.20", ReportCategory.OVERCHARGING),
    ("Loose repacked spices sold without any declaration at all", ReportCategory.OTHER),
]


async def seed_citizen_reports(
    db: AsyncSession, users: dict[str, User], products: list[Product]
) -> None:
    consumers = [users[c[0]] for c in CONSUMERS]
    officers = [users[o[0]] for o in OFFICERS]

    for n in range(1, 49):
        reporter = RNG.choice(consumers)
        store = RNG.choice(STORES)
        remark, category = RNG.choice(REPORT_REMARKS)
        product = RNG.choice(products)
        created = ago(days=RNG.uniform(0, 60))

        roll = RNG.random()
        if roll < 0.35:
            status, verified_at = ReportStatus.VERIFIED, created + timedelta(days=RNG.uniform(0.5, 5))
        elif roll < 0.55:
            status, verified_at = ReportStatus.INVESTIGATING, None
        elif roll < 0.68:
            status, verified_at = ReportStatus.REJECTED, created + timedelta(days=RNG.uniform(0.5, 4))
        else:
            status, verified_at = ReportStatus.SUBMITTED, None

        claimed = product.official_mrp
        charged = (
            round(claimed * RNG.uniform(1.15, 1.7), 2)
            if claimed and category == ReportCategory.OVERCHARGING
            else None
        )

        db.add(
            CitizenReport(
                report_ref=f"rep_{1000 + n}",
                reporter_id=reporter.id,
                store_name=store["name"],
                store_address=store["address"],
                latitude=store["lat"] + RNG.uniform(-0.001, 0.001),
                longitude=store["lng"] + RNG.uniform(-0.001, 0.001),
                violation_category=category,
                citizen_remarks=remark,
                image_path=f"uploads/demo/report_{1000 + n}.jpg",
                barcode=product.barcode,
                claimed_mrp=claimed,
                charged_price=charged,
                status=status,
                priority_score=reporter.citizen_trust_score,
                assigned_officer_id=RNG.choice(officers).id if status != ReportStatus.SUBMITTED else None,
                officer_notes=(
                    "Field visit conducted; violation confirmed and notice issued."
                    if status == ReportStatus.VERIFIED
                    else (
                        "Could not substantiate the claim during inspection."
                        if status == ReportStatus.REJECTED
                        else None
                    )
                ),
                verified_at=verified_at,
                created_at=created,
            )
        )

    # Keep reporter counters consistent with the reports just written
    for c in consumers:
        c.reports_submitted = RNG.randint(2, 14)
        c.reports_confirmed = RNG.randint(0, c.reports_submitted)
    await db.flush()


async def seed_peer_reviews(
    db: AsyncSession, users: dict[str, User], sessions: list[InspectionSession]
) -> None:
    seniors = [users["senior.iyer"], users["senior.chauhan"]]
    escalated = [s for s in sessions if s.status == SessionStatus.PEER_REVIEW]

    for s in escalated:
        conf = s.confidence_score or 0.7
        penalty = s.estimated_penalty or 0.0
        if penalty > settings.PEER_REVIEW_PENALTY_THRESHOLD:
            trigger, detail = (
                PeerReviewTrigger.HIGH_PENALTY,
                f"Aggregate penalty exposure Rs.{penalty:,.0f} exceeds the "
                f"Rs.{settings.PEER_REVIEW_PENALTY_THRESHOLD:,.0f} senior-review threshold.",
            )
        elif conf < settings.CONFIDENCE_ACCEPT_THRESHOLD:
            trigger, detail = (
                PeerReviewTrigger.LOW_CONFIDENCE,
                f"Pipeline confidence {conf:.2f} falls in the "
                f"{settings.CONFIDENCE_REVIEW_FLOOR:.2f}-"
                f"{settings.CONFIDENCE_ACCEPT_THRESHOLD:.2f} escalation band.",
            )
        else:
            trigger, detail = (
                PeerReviewTrigger.CONTESTED_UNIT_PRICE,
                "Unit sale price computation contested against the declared net quantity.",
            )

        decided = RNG.random() < 0.45
        outcome = RNG.choice(
            [PeerReviewStatus.APPROVED, PeerReviewStatus.REJECTED, PeerReviewStatus.MODIFIED]
        )
        db.add(
            PeerReview(
                session_id=s.id,
                requested_by_id=s.officer_id,
                reviewer_id=RNG.choice(seniors).id,
                trigger_reason=trigger,
                trigger_detail=detail,
                triggering_confidence=conf,
                review_status=outcome if decided else PeerReviewStatus.PENDING,
                reviewer_remarks=(
                    {
                        PeerReviewStatus.APPROVED: "Pixel crops reviewed. Findings sustained; notice approved for issue.",
                        PeerReviewStatus.REJECTED: "Evidence insufficient on the cited panel. Case dismissed with remarks.",
                        PeerReviewStatus.MODIFIED: "Font-height finding downgraded to advisory; remaining findings sustained.",
                    }[outcome]
                    if decided
                    else None
                ),
                reviewed_at=s.created_at + timedelta(days=RNG.uniform(0.5, 6)) if decided else None,
                created_at=s.created_at + timedelta(hours=RNG.uniform(1, 20)),
            )
        )
    await db.flush()


async def seed_brand_workflows(
    db: AsyncSession, users: dict[str, User], sessions: list[InspectionSession]
) -> None:
    brand_users = {users[u].brand_name: users[u] for u, _b, _e in BRANDS}

    # --- disputes against real flagged sessions ---
    disputable = [
        s
        for s in sessions
        if s.brand_name in brand_users
        and s.status in (SessionStatus.FLAGGED, SessionStatus.PEER_REVIEW)
    ][:14]

    for s in disputable:
        brand = brand_users[s.brand_name]
        created = s.created_at + timedelta(days=RNG.uniform(1, 8))
        submitted = RNG.random() < 0.7
        decided = submitted and RNG.random() < 0.5
        outcome = RNG.choice([AppellateStatus.ACCEPTED, AppellateStatus.REJECTED])

        db.add(
            BrandDispute(
                session_id=s.id,
                brand_id=brand.id,
                brand_name=s.brand_name,
                dispute_token=generate_token("dsp"),
                token_expires_at=created + timedelta(days=settings.DISPUTE_WINDOW_DAYS),
                grounds_of_appeal=(
                    "Packaging variation was approved under the Legal Metrology "
                    "(Packaged Commodities) Amendment Rules 2024. Batch records and an "
                    "accredited laboratory declaration are attached in support."
                )
                if submitted
                else None,
                counter_evidence_urls=(
                    [
                        f"appeals/{s.session_id}_batch_record.pdf",
                        f"appeals/{s.session_id}_lab_certificate.pdf",
                    ]
                    if submitted
                    else None
                ),
                appellate_status=outcome if decided else AppellateStatus.UNDER_REVIEW,
                appellate_officer_id=users["senior.iyer"].id if decided else None,
                appellate_remarks=(
                    "Counter-evidence accepted; notice withdrawn."
                    if outcome == AppellateStatus.ACCEPTED
                    else "Counter-evidence does not address the cited declaration. Notice upheld."
                )
                if decided
                else None,
                hearing_date=created + timedelta(days=RNG.uniform(10, 30)),
                decided_at=created + timedelta(days=RNG.uniform(5, 20)) if decided else None,
                created_at=created,
            )
        )

    # --- pre-market self-certifications ---
    artwork = [
        ("Parle Products", "Parle-G Gold 500g New Artwork"),
        ("Britannia Industries", "Britannia NutriChoice Digestive 400g"),
        ("Adani Wilmar", "Fortune Rice Bran Health Oil 5L Jerry Can"),
        ("MDH", "MDH Kitchen King Masala 200g Carton"),
        ("Haldiram's", "Haldiram Premium Kaju Katli Diwali Box"),
        ("Parle Products", "Parle Hide & Seek Fills 100g"),
        ("Britannia Industries", "Britannia Milk Bikis 300g Refresh"),
    ]
    for i, (brand_name, product_name) in enumerate(artwork, start=1):
        brand = brand_users[brand_name]
        approved = RNG.random() < 0.6
        score = RNG.randint(92, 100) if approved else RNG.randint(58, 88)
        findings = (
            []
            if approved
            else [
                {
                    "rule": "R-FONT-HEIGHT",
                    "clause": LEGAL_CLAUSES["font_height"],
                    "severity": "MAJOR",
                    "message": "Net quantity numerals are 1.6 mm; Rule 11 requires 2.0 mm for this panel area.",
                    "fix": "Increase net quantity type size to at least 2.0 mm cap height.",
                },
                {
                    "rule": "R-UNIT-PRICE",
                    "clause": LEGAL_CLAUSES["unit_price"],
                    "severity": "MINOR",
                    "message": "Unit sale price is absent from the principal display panel.",
                    "fix": "Add unit sale price adjacent to the retail sale price.",
                },
            ]
        )
        db.add(
            BrandPreCert(
                cert_ref=f"cert_{4400 + i}",
                brand_id=brand.id,
                brand_name=brand_name,
                product_name=product_name,
                die_line_file_path=f"dieline/demo/cert_{4400 + i}.pdf",
                sha256_hash=sha256_bytes(f"dieline-{i}".encode()),
                target_pack_width_cm=round(RNG.uniform(8, 24), 1),
                target_pack_height_cm=round(RNG.uniform(12, 32), 1),
                compliance_score=score,
                is_approved=approved,
                findings=findings,
                digital_badge_token=generate_token("badge") if approved else None,
                badge_qr_path=f"certs/demo/badge_{4400 + i}.png" if approved else None,
                audit_report_pdf_path=f"certs/demo/cert_{4400 + i}.pdf",
                created_at=ago(days=RNG.uniform(2, 90)),
            )
        )
    await db.flush()


async def seed_ecom(db: AsyncSession, products: list[Product]) -> None:
    platforms = list(EcomPlatform)
    for product in RNG.sample(products, k=60):
        for platform in RNG.sample(platforms, k=RNG.randint(1, 3)):
            physical = product.official_mrp or 100.0
            # Dark-pattern markup on a minority of listings
            gouged = RNG.random() < 0.28
            listed = round(physical * RNG.uniform(1.10, 1.75), 2) if gouged else physical
            origin_ok = RNG.random() > 0.18
            qty_ok = RNG.random() > 0.12
            online_qty = product.net_quantity if qty_ok else f"{RNG.randint(1, 5)} pack"

            notes = []
            if gouged:
                notes.append(
                    f"Listed MRP Rs.{listed:.2f} exceeds verified physical pack MRP Rs.{physical:.2f}"
                )
            if not origin_ok:
                notes.append("Country of origin not declared on the listing (Rule 6(10))")
            if not qty_ok:
                notes.append(
                    f"Listed net quantity '{online_qty}' does not match pack '{product.net_quantity}'"
                )

            db.add(
                EcomListingCrosscheck(
                    product_id=product.id,
                    barcode=product.barcode,
                    platform_name=platform.value,
                    listing_url=(
                        f"https://www.{platform.value.lower().replace(' ', '')}.example/dp/"
                        f"{product.barcode}"
                    ),
                    listing_title=f"{product.product_name} - {product.net_quantity}",
                    scraped_mrp=listed,
                    physical_pack_mrp=physical,
                    mrp_discrepancy=gouged,
                    country_of_origin_found=origin_ok,
                    online_net_qty=online_qty,
                    physical_net_qty=product.net_quantity,
                    net_qty_discrepancy=not qty_ok,
                    manufacturer_found=RNG.random() > 0.1,
                    customer_care_found=RNG.random() > 0.15,
                    is_compliant=not notes,
                    violation_notes=" | ".join(notes) or None,
                    last_checked_at=ago(days=RNG.uniform(0, 14)),
                )
            )
    await db.flush()


async def seed_agency_graph(db: AsyncSession, products: list[Product]) -> None:
    brands = sorted({p.brand_name for p in products})
    for brand in brands:
        members = [p for p in products if p.brand_name == brand]
        avg = sum(p.avg_score or 85 for p in members) / len(members)
        violations = sum(p.violation_count for p in members)

        # Risk index is what the routing engine multiplies store risk by.
        risk = round(max(0.0, min(10.0, (100 - avg) / 10 + violations * 0.15)), 2)
        troubled = risk > 4.0

        db.add(
            CrossAgencyLink(
                brand_name=brand,
                legal_entity_name=f"{brand} Private Limited",
                fssai_number=members[0].fssai_number,
                fssai_valid=not (troubled and RNG.random() < 0.4),
                fssai_expiry=ago(days=-RNG.uniform(-200, 700)),
                bis_reg_number=f"BIS/{RNG.randint(100000, 999999)}",
                bis_valid=not (troubled and RNG.random() < 0.3),
                gstin=f"{RNG.randint(1, 37):02d}AAACP{RNG.randint(1000, 9999)}Q1Z{RNG.randint(0, 9)}",
                gstin_active=not (troubled and RNG.random() < 0.25),
                risk_index=risk,
                lm_violation_count=violations,
                escalation_notes=(
                    "Repeat packaging non-compliance detected; flagged for inter-agency review."
                    if troubled
                    else None
                ),
                last_synced_at=ago(days=RNG.uniform(0, 10)),
            )
        )
    await db.flush()


async def seed_alerts(db: AsyncSession, users: dict[str, User], products: list[Product]) -> None:
    consumers = [users[c[0]] for c in CONSUMERS]
    flagged = [p for p in products if (p.avg_score or 100) < 70]

    templates = [
        (AlertType.PRODUCT_RECALL, "CRITICAL", "Product recall notice",
         "A batch of {name} has been recalled following a Legal Metrology enforcement action. "
         "Please check the batch code printed on your pack."),
        (AlertType.EXPIRED_BATCH_WARNING, "WARNING", "Expired stock reported nearby",
         "Expired packs of {name} were reported at a retailer close to your last scan location."),
        (AlertType.PRICE_SURGE, "WARNING", "Overcharging detected near you",
         "{name} is being sold above its printed MRP at retailers in your area. "
         "The verified MRP is Rs.{mrp:.2f}."),
        (AlertType.COMPLIANCE_UPDATE, "INFO", "Compliance score updated",
         "The compliance score for {name} changed after a recent field inspection."),
    ]

    for consumer in consumers:
        for _ in range(RNG.randint(2, 6)):
            product = RNG.choice(flagged or products)
            alert_type, severity, title, body = RNG.choice(templates)
            db.add(
                ConsumerAlert(
                    user_id=consumer.id,
                    barcode=product.barcode,
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    message=body.format(name=product.product_name, mrp=product.official_mrp or 0),
                    action_url=f"/consumer/scan?barcode={product.barcode}",
                    is_read=RNG.random() < 0.4,
                    created_at=ago(days=RNG.uniform(0, 30)),
                )
            )
    await db.flush()


# ===========================================================================
# Orchestration
# ===========================================================================
async def run(reset: bool = False) -> None:
    if reset:
        print("  Dropping existing schema ...")
        await drop_db()
    await init_db()

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count(User.id)))).scalar_one()
        if existing and not reset:
            print(f"  Database already has {existing} users. Use --reset to rebuild.")
            return

        print("  Seeding users ...")
        users = await seed_users(db)

        print("  Seeding categories & products ...")
        cats, products = await seed_catalogue(db)

        print("  Seeding inspection history ...")
        sessions = await seed_inspections(db, users, products)

        print("  Seeding price-gouging radar corpus ...")
        await seed_price_history(db, users, products)

        print("  Seeding citizen reports ...")
        await seed_citizen_reports(db, users, products)

        print("  Seeding peer-review queue ...")
        await seed_peer_reviews(db, users, sessions)

        print("  Seeding brand disputes & pre-certifications ...")
        await seed_brand_workflows(db, users, sessions)

        print("  Seeding e-commerce cross-checks ...")
        await seed_ecom(db, products)

        print("  Seeding inter-agency regulatory graph ...")
        await seed_agency_graph(db, products)

        print("  Seeding consumer alerts ...")
        await seed_alerts(db, users, products)

        await db.commit()

        # ---- summary ----
        from models import (
            BrandDispute as _BD,
            BrandPreCert as _BC,
            CitizenReport as _CR,
            ConsumerAlert as _CA,
            CrossAgencyLink as _CG,
            EcomListingCrosscheck as _EL,
            ExtractedField as _EF,
            PeerReview as _PR,
            PriceHistoryScan as _PH,
            SessionImage as _SI,
            Violation as _VI,
        )

        counts = {}
        for label, model in [
            ("users", User), ("categories", Category), ("products", Product),
            ("inspection_sessions", InspectionSession), ("session_images", _SI),
            ("extracted_fields", _EF), ("violations", _VI),
            ("price_history_scans", _PH), ("citizen_reports", _CR),
            ("peer_reviews", _PR), ("brand_disputes", _BD),
            ("brand_pre_certifications", _BC), ("ecom_listings", _EL),
            ("cross_agency_links", _CG), ("consumer_alerts", _CA),
        ]:
            counts[label] = (await db.execute(select(func.count(model.id)))).scalar_one()

        anomalies = (
            await db.execute(
                select(func.count(_PH.id)).where(_PH.is_anomalous.is_(True))
            )
        ).scalar_one()
        pending_reviews = (
            await db.execute(
                select(func.count(_PR.id)).where(_PR.review_status == PeerReviewStatus.PENDING)
            )
        ).scalar_one()

        print("\n" + "=" * 60)
        print("  SEED COMPLETE")
        print("=" * 60)
        for k, v in counts.items():
            print(f"  {k:28} {v:>6}")
        print("-" * 60)
        print(f"  {'price anomalies flagged':28} {anomalies:>6}")
        print(f"  {'peer reviews pending':28} {pending_reviews:>6}")
        print("=" * 60)
        print(f"\n  Demo password for every account: {DEMO_PASSWORD}\n")
        print("  admin           admin")
        print("  officer         officer.sharma / officer.verma / officer.khan / officer.reddy")
        print("  senior officer  senior.iyer / senior.chauhan")
        print("  consumer        citizen.priya (trust 92) ... citizen.ananya (trust 30)")
        print("  brand           brand.parle / brand.britannia / brand.fortune / "
              "brand.mdh / brand.haldiram\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the MetriX demo database")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))


if __name__ == "__main__":
    main()
