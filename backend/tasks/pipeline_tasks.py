"""Multi-surface inspection pipeline -- spec tasks/pipeline_tasks.py, WORKER 1.

The six stages from the reference deck, in order:

    1 CAPTURE     surfaces already uploaded and hash-sealed
    2 PREPROCESS  EXIF -> curvature -> unwarp -> enhance
    3 AI EXTRACT  vision LLM proposes declarations with bounding boxes
    4 VERIFY      OCR re-reads each cited crop; coordinates mapped to the original
    5 VALIDATE    deterministic rules engine
    6 REVIEW      confidence fusion decides accept / escalate / reject

Written as a plain function so it runs identically under Celery and under the
in-process dev runner, and so it can be called directly from a test.

Progress is published over WebSocket at every stage, because an officer standing
in a shop needs to see the inspection moving, not a spinner.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.config import settings
from core.storage import get_storage
from core.task_runner import QUEUE_INSPECTION, task
from core.websocket_manager import emit
from extraction import barcode as barcode_mod
from extraction.confidence import Verdict, fuse_field, fuse_session
from extraction.gs1_validator import validate_ean
from extraction.ocr_verify import get_verifier
from extraction.schemas import FIELD_NAMES
from extraction.vision_llm import get_provider
from models.enums import SessionStatus, SurfaceType
from preprocessing import contour, cylindrical_unwarp, enhance, planar_unwarp
from preprocessing.coordinate_mapper import (
    BBox,
    CoordinateMapper,
    crop_region,
    font_height_mm,
    measure_ink_height_px,
)
from preprocessing.exif import correct_orientation, to_bytes
from rules.base import RuleContext
from rules.registry import evaluate as evaluate_rules

logger = logging.getLogger("metrix.pipeline")

STAGE_CAPTURE = "CAPTURE"
STAGE_PREPROCESS = "PREPROCESS"
STAGE_EXTRACT = "EXTRACT"
STAGE_VERIFY = "VERIFY"
STAGE_VALIDATE = "VALIDATE"
STAGE_REVIEW = "REVIEW"


@dataclass
class SurfaceOutcome:
    """Everything the pipeline learned from one photographed surface."""

    surface_type: str
    image_key: str
    original: np.ndarray | None = None
    rectified: np.ndarray | None = None
    mapper: CoordinateMapper | None = None
    unwarp_method: str = "none"
    curvature: float = 0.0
    px_per_mm: float | None = None
    transformation: dict | None = None
    barcode: str | None = None
    barcode_symbology: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class PipelineOutcome:
    session_id: str
    status: str
    score: int = 0
    compliance_status: str = "COMPLIANT"
    confidence: float = 0.0
    verdict: str = Verdict.REJECT
    total_penalty: float = 0.0
    barcode: str | None = None
    barcode_verified: bool = False
    surfaces: list[SurfaceOutcome] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    escalation_triggers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    timings_ms: dict[str, int] = field(default_factory=dict)


# ===========================================================================
# Stage 2 -- preprocessing
# ===========================================================================
def preprocess_surface(
    image_bytes: bytes,
    surface_type: str,
    image_key: str,
    pack_width_cm: float | None,
    pack_height_cm: float | None,
) -> SurfaceOutcome:
    """EXIF -> curvature -> rectify -> enhance, retaining the inverse transform."""
    out = SurfaceOutcome(surface_type=surface_type, image_key=image_key)

    ex = correct_orientation(image_bytes)
    out.original = ex.image
    original_size = (ex.image.shape[1], ex.image.shape[0])

    det = contour.analyse(ex.image)
    out.curvature = det.curvature_score

    if det.method == contour.CYLINDRICAL:
        arc = cylindrical_unwarp.estimate_visible_arc(ex.image, det.corners)
        un, _maps = cylindrical_unwarp.unwarp(ex.image, det.corners, visible_arc_deg=arc)
        transform_payload = (
            {"method": "cylindrical", "forward": un.matrix.tolist(),
             "output_size": list(un.output_size)}
            if un.matrix is not None else None
        )
    elif det.method == contour.PLANAR:
        un = planar_unwarp.unwarp(ex.image, det.corners)
        transform_payload = un.matrix_as_json()
    else:
        un = planar_unwarp.unwarp(ex.image, None)
        transform_payload = None

    out.unwarp_method = un.method
    out.transformation = transform_payload
    out.mapper = CoordinateMapper(
        method=un.method,
        transform=transform_payload,
        original_size=original_size,
        rectified_size=un.output_size,
    )

    # Physical scale for Rule 11. Derived from the RECTIFIED image, because the
    # stated pack dimensions describe the flat pack, not its projection.
    if det.corners is not None and pack_width_cm and pack_height_cm:
        if un.applied:
            out.px_per_mm = round(
                (
                    un.output_size[0] / (pack_width_cm * 10)
                    + un.output_size[1] / (pack_height_cm * 10)
                )
                / 2,
                4,
            )
        else:
            out.px_per_mm = contour.estimate_px_per_mm(
                det.corners, pack_width_cm, pack_height_cm
            )

    enhanced = enhance.enhance(un.image)
    out.rectified = enhanced.enhanced
    out.warnings.extend(enhanced.warnings)
    if not det.detected:
        out.warnings.append(det.reason)

    # Barcode is read from the ORIGINAL frame: rectification resamples the bars
    # and can destroy a symbol that was perfectly decodable before.
    bc = barcode_mod.detect(ex.image)
    if bc.found:
        out.barcode = bc.data
        out.barcode_symbology = bc.symbology
        if bc.checksum_valid is False:
            out.warnings.append(bc.note)

    return out


# ===========================================================================
# Stages 3 & 4 -- extract, then verify against the same pixels
# ===========================================================================
def extract_and_verify(
    surface: SurfaceOutcome,
    session_id: str,
    persist_crops: bool = True,
) -> dict[str, dict]:
    """Ask the model what it sees, then check the pixels actually say that."""
    provider = get_provider()
    verifier = get_verifier()
    storage = get_storage()

    # Some providers derive their readings FROM the OCR engine -- the mock, and
    # the NVIDIA path, which has OCR read the characters and uses the model only
    # to label the lines. Re-reading the same crop with that same engine is not
    # independent verification: it agrees with itself by construction,
    # manufacturing confidence the system has not earned. Such fields are
    # recorded as unverified, which caps their confidence below the auto-accept
    # threshold and routes the session to human review.
    #
    # The provider declares this about itself rather than being identified by
    # name here, so a new OCR-backed provider cannot be added without answering
    # the question.
    self_verifying = getattr(provider, "self_verifying", False)

    result = provider.extract(surface.rectified, surface=surface.surface_type)
    if not result.succeeded:
        surface.error = result.error
        logger.warning("Vision extraction failed on %s: %s", surface.surface_type, result.error)
        return {}

    found: dict[str, dict] = {}

    for f in result.fields:
        if not f.is_present or f.value is None:
            continue

        record: dict[str, Any] = {
            "field_name": f.field_name,
            "detected_value": f.value,
            "surface_found": surface.surface_type,
            "confidence_vision_llm": f.confidence,
            "confidence_ocr_verify": None,
            "ocr_agreement": None,
            "ocr_read_value": None,
            "raw_pixel_crop_path": None,
            "font_height_mm": None,
            "bbox": None,
            "provider": result.provider,
        }

        if f.bbox is not None:
            rect_box = BBox(f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height)

            # Verify against the crop the model actually looked at.
            if self_verifying:
                record["verification_note"] = (
                    "Extraction was produced by the OCR engine itself; no "
                    "independent re-read is possible with this provider"
                )
            else:
                crop = crop_region(surface.rectified, rect_box, padding=6)
                verification = verifier.verify(crop, f.field_name, f.value)
                record["confidence_ocr_verify"] = verification.confidence
                record["ocr_agreement"] = (
                    None if verification.engine == "morphology" else verification.agrees
                )
                record["ocr_read_value"] = verification.ocr_value

            # Map the box back to ORIGINAL camera pixels. The notice must cite
            # the officer's untouched photograph, not a rectified derivative.
            mapped = surface.mapper.map_bbox(rect_box) if surface.mapper else None
            if mapped:
                record["bbox"] = mapped.bbox.as_tuple()
                record["polygon"] = mapped.polygon
                if persist_crops and surface.original is not None:
                    evidence = crop_region(surface.original, mapped.bbox, padding=10)
                    if evidence.size:
                        key = (
                            f"crops/{session_id}/"
                            f"{surface.surface_type}_{f.field_name}.png"
                        )
                        try:
                            storage.save(key, to_bytes(evidence, fmt="PNG"), "image/png")
                            record["raw_pixel_crop_path"] = key
                        except Exception as exc:
                            logger.warning("Could not store evidence crop: %s", exc)

            # Character height in millimetres, for Rule 11. Measured from the
            # ink itself rather than the detector's box, which carries padding
            # and would over-report the height a finding depends on.
            ink_px = measure_ink_height_px(
                crop_region(surface.rectified, rect_box, padding=0)
            )
            record["font_height_mm"] = font_height_mm(
                ink_px or rect_box.height, surface.px_per_mm, box_kind="ink"
            )

        found[f.field_name] = record

    surface.fields = found
    return found


# ===========================================================================
# Orchestration
# ===========================================================================
def run_pipeline(
    session_id: str,
    images: list[tuple[str, bytes, str]],
    pack_width_cm: float | None = None,
    pack_height_cm: float | None = None,
    category_slug: str | None = None,
    inspection_date: datetime | None = None,
    is_pre_certification: bool = False,
    persist_crops: bool = True,
) -> PipelineOutcome:
    """Run all six stages over one session's surfaces.

    `images` is [(surface_type, image_bytes, image_key)].
    """
    started = datetime.now(timezone.utc)
    outcome = PipelineOutcome(session_id=session_id, status=SessionStatus.PROCESSING)

    try:
        # ------------------------------------------------ 1 CAPTURE --------
        emit(session_id, STAGE_CAPTURE, "completed", 10,
             f"{len(images)} surface(s) received and hash-sealed",
             surfaces=[s for s, _b, _k in images])

        if not images:
            outcome.status = SessionStatus.FAILED
            outcome.error = "No surfaces were supplied for inspection"
            return outcome

        # -------------------------------------------- 2 PREPROCESS --------
        t0 = datetime.now(timezone.utc)
        surfaces: list[SurfaceOutcome] = []
        for i, (surface_type, data, key) in enumerate(images):
            emit(session_id, STAGE_PREPROCESS, "progress",
                 10 + int(20 * (i / max(len(images), 1))),
                 f"Preprocessing {surface_type} surface ({i + 1} of {len(images)})")
            try:
                s = preprocess_surface(data, surface_type, key, pack_width_cm, pack_height_cm)
                surfaces.append(s)
                emit(session_id, STAGE_PREPROCESS, "progress",
                     10 + int(20 * ((i + 1) / max(len(images), 1))),
                     f"{surface_type}: {s.unwarp_method} rectification"
                     + (f", {s.px_per_mm} px/mm" if s.px_per_mm else ""),
                     surface=surface_type, method=s.unwarp_method,
                     curvature=s.curvature)
            except Exception as exc:
                logger.exception("Preprocessing failed for %s", surface_type)
                failed = SurfaceOutcome(surface_type=surface_type, image_key=key,
                                        error=str(exc))
                surfaces.append(failed)

        outcome.surfaces = surfaces
        outcome.timings_ms["preprocess"] = int(
            (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        )
        emit(session_id, STAGE_PREPROCESS, "completed", 30, "Preprocessing complete")

        # ----------------------------------- 3 EXTRACT + 4 VERIFY ---------
        t0 = datetime.now(timezone.utc)
        provider_name = get_provider().name
        merged: dict[str, dict] = {}

        for i, s in enumerate(surfaces):
            if s.rectified is None:
                continue
            emit(session_id, STAGE_EXTRACT, "progress",
                 30 + int(30 * (i / max(len(surfaces), 1))),
                 f"Reading declarations from the {s.surface_type} surface "
                 f"({provider_name})",
                 surface=s.surface_type, provider=provider_name)

            fields = extract_and_verify(s, session_id, persist_crops=persist_crops)

            # Merge across surfaces, keeping the better-evidenced reading when
            # the same declaration appears on more than one panel.
            for name, record in fields.items():
                existing = merged.get(name)
                if existing is None:
                    merged[name] = record
                    continue
                new_score = (record.get("confidence_vision_llm") or 0) + (
                    0.3 if record.get("ocr_agreement") else 0
                )
                old_score = (existing.get("confidence_vision_llm") or 0) + (
                    0.3 if existing.get("ocr_agreement") else 0
                )
                if new_score > old_score:
                    merged[name] = record

            emit(session_id, STAGE_VERIFY, "progress",
                 45 + int(20 * ((i + 1) / max(len(surfaces), 1))),
                 f"{s.surface_type}: {len(fields)} declarations read and "
                 "cross-checked against the source pixels",
                 surface=s.surface_type, found=sorted(fields))

        outcome.timings_ms["extract"] = int(
            (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        )
        emit(session_id, STAGE_VERIFY, "completed", 65,
             f"{len(merged)} declarations extracted and verified")

        # ------------------------------------------------- barcode --------
        for s in surfaces:
            if s.barcode:
                outcome.barcode = s.barcode
                check = validate_ean(s.barcode)
                outcome.barcode_verified = bool(check.checksum_valid)
                break

        # --------------------------------------------- 5 VALIDATE ---------
        t0 = datetime.now(timezone.utc)
        emit(session_id, STAGE_VALIDATE, "started", 70,
             "Applying the Legal Metrology rules engine")

        field_values = {name: rec.get("detected_value") for name, rec in merged.items()}
        for name in FIELD_NAMES:
            field_values.setdefault(name, None)

        font_heights = {
            name: rec["font_height_mm"]
            for name, rec in merged.items()
            if rec.get("font_height_mm")
        }

        area = None
        if pack_width_cm and pack_height_cm:
            area = pack_width_cm * pack_height_cm

        gs1 = validate_ean(outcome.barcode) if outcome.barcode else None

        ctx = RuleContext(
            fields=field_values,
            raw_fields={
                name: type("Row", (), {
                    "raw_pixel_crop_path": rec.get("raw_pixel_crop_path"),
                    "surface_found": rec.get("surface_found"),
                    "effective_confidence": rec.get("confidence_vision_llm") or 1.0,
                })()
                for name, rec in merged.items()
            },
            surfaces=[s.surface_type for s in surfaces],
            surface_area_cm2=area,
            package_width_cm=pack_width_cm,
            package_height_cm=pack_height_cm,
            font_heights_mm=font_heights,
            barcode=outcome.barcode,
            barcode_verified=outcome.barcode_verified,
            category_slug=category_slug,
            inspection_date=(inspection_date or started).date(),
            is_pre_certification=is_pre_certification,
            metadata={"gs1_country": gs1.issuing_country if gs1 else None},
        )

        ev = evaluate_rules(ctx)
        outcome.score = ev.score
        outcome.compliance_status = ev.compliance_status
        outcome.total_penalty = ev.total_penalty
        outcome.timings_ms["validate"] = int(
            (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        )

        emit(session_id, STAGE_VALIDATE, "completed", 85,
             f"{len(ev.results)} rules evaluated: {len(ev.failures)} failed, "
             f"{len(ev.warnings)} warnings",
             score=ev.score, compliance=ev.compliance_status)

        # ----------------------------------------------- 6 REVIEW ---------
        emit(session_id, STAGE_REVIEW, "started", 90, "Fusing confidence and deciding disposition")

        field_confidences = [
            fuse_field(
                name,
                rec.get("confidence_vision_llm") or 0.0,
                rec.get("confidence_ocr_verify"),
                rec.get("ocr_agreement"),
                None,
            )
            for name, rec in merged.items()
        ]
        session_conf = fuse_session(
            field_confidences,
            estimated_penalty=ev.total_penalty,
            has_contested_unit_price=ev.has_contested_unit_price,
        )

        outcome.confidence = session_conf.overall
        outcome.verdict = session_conf.verdict
        outcome.escalation_triggers = session_conf.triggers

        if session_conf.verdict == Verdict.PEER_REVIEW:
            outcome.status = SessionStatus.PEER_REVIEW
        elif session_conf.verdict == Verdict.REJECT:
            outcome.status = SessionStatus.FAILED
        elif ev.failures:
            outcome.status = SessionStatus.FLAGGED
        else:
            outcome.status = SessionStatus.COMPLETED

        # ------------------------------------------------ assemble --------
        for name, rec in merged.items():
            fc = next((c for c in field_confidences if c.field_name == name), None)
            outcome.fields.append({
                **rec,
                "fused_confidence": fc.fused if fc else None,
                "verdict": fc.verdict if fc else None,
            })

        outcome.violations = [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "field_name": r.field_name,
                "status": r.status,
                "evidence_text": r.evidence_text,
                "legal_clause": r.legal_clause,
                "severity": r.severity,
                "confidence": r.confidence,
                "calculated_value": r.calculated_value,
                "expected_value": r.expected_value,
                "discrepancy": r.discrepancy,
                "suggested_fix": r.suggested_fix,
                "penalty_amount": r.penalty_amount,
                "evidence_crop_path": r.evidence_crop_path,
                "surface": r.surface,
            }
            for r in ev.results
            if r.is_violation
        ]

        for s in surfaces:
            outcome.warnings.extend(f"{s.surface_type}: {w}" for w in s.warnings)

        outcome.timings_ms["total"] = int(
            (datetime.now(timezone.utc) - started).total_seconds() * 1000
        )

        emit(session_id, STAGE_REVIEW, "completed", 100,
             session_conf.rationale,
             verdict=session_conf.verdict, score=ev.score,
             confidence=session_conf.overall, session_status=outcome.status,
             violations=len(outcome.violations))

        return outcome

    except Exception as exc:  # pragma: no cover - top-level guard
        logger.error("Pipeline failed for %s:\n%s", session_id, traceback.format_exc())
        outcome.status = SessionStatus.FAILED
        outcome.error = f"{exc.__class__.__name__}: {exc}"
        emit(session_id, STAGE_REVIEW, "failed", 100, f"Inspection failed: {exc}")
        return outcome


# ===========================================================================
# Registered task -- persists the outcome
# ===========================================================================
@task("pipeline.process_session", queue=QUEUE_INSPECTION)
def process_session(session_db_id: int) -> dict:
    """Load a session's surfaces, run the pipeline, and write the results back."""
    return asyncio.run(_process_session_async(session_db_id))


async def _process_session_async(session_db_id: int) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from models.extracted_field import ExtractedField
    from models.inspection_session import InspectionSession
    from models.session_image import SessionImage
    from models.violation import Violation

    storage = get_storage()

    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(
                select(InspectionSession)
                .where(InspectionSession.id == session_db_id)
                .options(selectinload(InspectionSession.images))
            )
        ).scalar_one_or_none()

        if session is None:
            return {"error": f"session {session_db_id} not found"}

        session.status = SessionStatus.PROCESSING
        await db.commit()

        images: list[tuple[str, bytes, str]] = []
        for img in session.images:
            try:
                images.append((img.surface_type, storage.read(img.image_path), img.image_path))
            except Exception as exc:
                logger.warning("Could not read %s: %s", img.image_path, exc)

        category_slug = None
        if session.category_id:
            from models.category import Category

            cat = (
                await db.execute(select(Category).where(Category.id == session.category_id))
            ).scalar_one_or_none()
            category_slug = cat.slug if cat else None

    # The pipeline is CPU-bound and synchronous; it deliberately holds no
    # database session while it runs.
    outcome = run_pipeline(
        session_id=session.session_id,
        images=images,
        pack_width_cm=session.package_width_cm,
        pack_height_cm=session.package_height_cm,
        category_slug=category_slug,
        inspection_date=session.created_at,
    )

    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(
                select(InspectionSession).where(InspectionSession.id == session_db_id)
            )
        ).scalar_one()

        # Persist what preprocessing determined about each surface. The
        # transformation matrix in particular is not a diagnostic -- it is what
        # lets a later reviewer (or a court) re-derive how a cited bounding box
        # maps onto the original photograph. Discarding it would make the
        # evidence chain unreproducible.
        by_key = {s.image_key: s for s in outcome.surfaces}
        for img in (
            await db.execute(
                select(SessionImage).where(SessionImage.session_id == session_db_id)
            )
        ).scalars():
            s = by_key.get(img.image_path)
            if s is None:
                continue
            img.unwarp_method = s.unwarp_method
            img.curvature_score = s.curvature
            img.is_curved_surface = s.unwarp_method == "cylindrical"
            img.transformation_matrix = s.transformation
            img.px_per_mm = s.px_per_mm

        session.status = outcome.status
        session.overall_score = outcome.score
        session.compliance_status = outcome.compliance_status
        session.confidence_score = outcome.confidence
        session.estimated_penalty = outcome.total_penalty or None
        session.processing_error = outcome.error
        session.completed_at = datetime.now(timezone.utc)
        if outcome.barcode:
            session.barcode = outcome.barcode
            session.barcode_verified = outcome.barcode_verified
        if outcome.status in (SessionStatus.COMPLETED, SessionStatus.FLAGGED):
            session.is_locked = True

        for rec in outcome.fields:
            bbox = rec.get("bbox") or (None, None, None, None)
            db.add(ExtractedField(
                session_id=session.id,
                field_name=rec["field_name"],
                detected_value=rec.get("detected_value"),
                normalized_value=rec.get("detected_value"),
                surface_found=rec.get("surface_found"),
                bbox_x=bbox[0], bbox_y=bbox[1],
                bbox_width=bbox[2], bbox_height=bbox[3],
                confidence_vision_llm=rec.get("confidence_vision_llm"),
                confidence_ocr_verify=rec.get("confidence_ocr_verify"),
                ocr_agreement=rec.get("ocr_agreement"),
                ocr_read_value=rec.get("ocr_read_value"),
                raw_pixel_crop_path=rec.get("raw_pixel_crop_path"),
                font_height_mm=rec.get("font_height_mm"),
                is_missing=False,
            ))

        for v in outcome.violations:
            db.add(Violation(session_id=session.id, **{
                k: v[k] for k in (
                    "rule_id", "rule_name", "field_name", "status", "evidence_text",
                    "legal_clause", "severity", "confidence", "calculated_value",
                    "expected_value", "discrepancy", "suggested_fix",
                    "penalty_amount", "evidence_crop_path",
                )
            }))

        # Persist the peer-review escalation required by spec 3.E.
        if outcome.status == SessionStatus.PEER_REVIEW and outcome.escalation_triggers:
            from models.peer_review import PeerReview

            first = outcome.escalation_triggers[0]
            db.add(PeerReview(
                session_id=session.id,
                requested_by_id=session.officer_id,
                trigger_reason=first.split(":")[0],
                trigger_detail="; ".join(outcome.escalation_triggers),
                triggering_confidence=outcome.confidence,
            ))

        await db.commit()

    return {
        "session_id": outcome.session_id,
        "status": outcome.status,
        "score": outcome.score,
        "compliance_status": outcome.compliance_status,
        "confidence": outcome.confidence,
        "violations": len(outcome.violations),
        "fields_extracted": len(outcome.fields),
        "penalty": outcome.total_penalty,
        "triggers": outcome.escalation_triggers,
        "timings_ms": outcome.timings_ms,
    }
