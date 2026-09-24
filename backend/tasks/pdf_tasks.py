"""PDF rendering tasks -- spec tasks/pdf_tasks.py, pdf_generation_queue."""
from __future__ import annotations

import asyncio
import logging

from core.storage import get_storage
from core.task_runner import QUEUE_PDF, task
from reports.pdf_builder import build_certificate, build_notice, build_policy_report, build_qr

logger = logging.getLogger("metrix.tasks.pdf")


@task("pdf.render_notice", queue=QUEUE_PDF)
def render_notice(session_db_id: int) -> dict:
    """Render the enforcement notice for a completed inspection."""
    return asyncio.run(_render_notice(session_db_id))


async def _render_notice(session_db_id: int) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import AsyncSessionLocal
    from models.brand_dispute import BrandDispute
    from models.inspection_session import InspectionSession

    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(
                select(InspectionSession)
                .where(InspectionSession.id == session_db_id)
                .options(
                    selectinload(InspectionSession.violations),
                    selectinload(InspectionSession.images),
                    selectinload(InspectionSession.officer),
                )
            )
        ).scalar_one_or_none()
        if session is None:
            return {"error": f"session {session_db_id} not found"}

        dispute = (
            await db.execute(
                select(BrandDispute).where(BrandDispute.session_id == session.id)
            )
        ).scalar_one_or_none()

        payload = {
            "session_id": session.session_id,
            "product_name": session.product_name,
            "brand_name": session.brand_name,
            "barcode": session.barcode,
            "product_category": session.product_category,
            "store_name": session.store_name,
            "location_address": session.location_address,
            "inspected_at": session.created_at.strftime("%d %B %Y, %H:%M")
            if session.created_at else None,
            "officer_name": session.officer.full_name if session.officer else None,
            "officer_id_code": session.officer.officer_id if session.officer else None,
            "jurisdiction_status": session.jurisdiction_status,
            "overall_score": session.overall_score,
            "compliance_status": session.compliance_status,
            "estimated_penalty": session.estimated_penalty,
            "evidence_seal": session.evidence_seal,
            "dispute_token": dispute.dispute_token if dispute else None,
            "violations": [
                {
                    "rule_id": v.rule_id, "rule_name": v.rule_name,
                    "severity": v.severity, "legal_clause": v.legal_clause,
                    "evidence_text": v.evidence_text,
                    "calculated_value": v.calculated_value,
                    "expected_value": v.expected_value,
                    "penalty_amount": v.penalty_amount,
                    "evidence_crop_path": v.evidence_crop_path,
                }
                for v in sorted(
                    (v for v in session.violations if v.status == "FAIL"),
                    key=lambda x: {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}.get(
                        x.severity or "MAJOR", 3
                    ),
                )
            ],
            "images": [
                {"surface_type": i.surface_type, "sha256_hash": i.sha256_hash}
                for i in session.images
            ],
        }

    pdf, engine = build_notice(payload)
    key = f"reports/{payload['session_id']}_notice.pdf"
    get_storage().save(key, pdf, "application/pdf")

    logger.info("Notice rendered for %s via %s (%d KB)",
                payload["session_id"], engine, len(pdf) // 1024)
    return {
        "session_id": payload["session_id"],
        "path": key,
        "engine": engine,
        "size_bytes": len(pdf),
        "violations": len(payload["violations"]),
    }


@task("pdf.render_pre_cert", queue=QUEUE_PDF)
def render_pre_cert(cert_db_id: int) -> dict:
    """Render a brand's Digital Compliance Certificate and QR badge."""
    return asyncio.run(_render_pre_cert(cert_db_id))


async def _render_pre_cert(cert_db_id: int) -> dict:
    from sqlalchemy import select

    from app.config import settings
    from app.database import AsyncSessionLocal
    from models.brand_pre_cert import BrandPreCert

    storage = get_storage()

    async with AsyncSessionLocal() as db:
        cert = (
            await db.execute(select(BrandPreCert).where(BrandPreCert.id == cert_db_id))
        ).scalar_one_or_none()
        if cert is None:
            return {"error": f"certificate {cert_db_id} not found"}

        payload = {
            "cert_ref": cert.cert_ref,
            "product_name": cert.product_name,
            "brand_name": cert.brand_name,
            "compliance_score": cert.compliance_score,
            "is_approved": cert.is_approved,
            "sha256_hash": cert.sha256_hash,
            "target_pack_width_cm": cert.target_pack_width_cm,
            "target_pack_height_cm": cert.target_pack_height_cm,
            "digital_badge_token": cert.digital_badge_token,
            "findings": cert.findings or [],
        }

        qr_key = None
        if cert.digital_badge_token:
            verify_url = f"/api/brand/verify-badge/{cert.digital_badge_token}"
            qr = build_qr(verify_url)
            if qr:
                qr_key = f"certs/{cert.cert_ref}_badge.png"
                storage.save(qr_key, qr, "image/png")
                payload["_qr_bytes"] = qr

        pdf, engine = build_certificate(payload)
        pdf_key = f"certs/{cert.cert_ref}.pdf"
        storage.save(pdf_key, pdf, "application/pdf")

        cert.audit_report_pdf_path = pdf_key
        if qr_key:
            cert.badge_qr_path = qr_key
        await db.commit()

    return {
        "cert_ref": payload["cert_ref"],
        "pdf": pdf_key,
        "qr": qr_key,
        "engine": engine,
        "approved": payload["is_approved"],
    }


@task("pdf.render_policy_report", queue=QUEUE_PDF)
def render_policy_report(days: int = 90) -> dict:
    """Render the ministry macro report."""
    return asyncio.run(_render_policy(days))


async def _render_policy(days: int) -> dict:
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://internal", timeout=120
    ) as client:
        # Reuse the same aggregation the dashboard uses so the PDF and the
        # screen can never disagree.
        from app.database import AsyncSessionLocal
        from routes.policy import macro_trends

        async with AsyncSessionLocal() as db:
            class _U:
                role = "admin"
                is_senior = True

            data = await macro_trends(db, _U(), days)  # type: ignore[arg-type]

    pdf, engine = build_policy_report(data)
    from datetime import datetime, timezone

    key = f"reports/policy_{datetime.now(timezone.utc):%Y%m%d}_{days}d.pdf"
    get_storage().save(key, pdf, "application/pdf")
    return {"path": key, "engine": engine, "window_days": days, "size_bytes": len(pdf)}
