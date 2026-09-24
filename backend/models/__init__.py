"""MetriX ORM layer -- the 15 tables of Final Production Architecture v3.0 section 4.

Importing this package is what populates ``Base.metadata``; both Alembic and the
dev bootstrap rely on that, so every model module must be imported here.
"""
from models.base import Base, JSONVariant, utcnow
from models.brand_dispute import BrandDispute
from models.brand_pre_cert import BrandPreCert
from models.category import Category
from models.citizen_report import CitizenReport
from models.consumer_alert import ConsumerAlert
from models.cross_agency import CrossAgencyLink
from models.ecom_listing import EcomListingCrosscheck
from models.extracted_field import ExtractedField
from models.inspection_session import InspectionSession
from models.peer_review import PeerReview
from models.price_history import PriceHistoryScan
from models.product import Product
from models.session_image import SessionImage
from models.user import User
from models.violation import Violation

__all__ = [
    "Base",
    "JSONVariant",
    "utcnow",
    "User",
    "Category",
    "Product",
    "InspectionSession",
    "SessionImage",
    "ExtractedField",
    "Violation",
    "PriceHistoryScan",
    "CitizenReport",
    "PeerReview",
    "BrandDispute",
    "BrandPreCert",
    "EcomListingCrosscheck",
    "CrossAgencyLink",
    "ConsumerAlert",
]
