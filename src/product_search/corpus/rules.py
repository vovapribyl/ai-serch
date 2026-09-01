from __future__ import annotations

from enum import StrEnum


class RejectionReason(StrEnum):
    INVALID_PRODUCT_ID = "INVALID_PRODUCT_ID"
    MISSING_CATEGORY = "MISSING_CATEGORY"
    MISSING_PRIMARY_IMAGE = "MISSING_PRIMARY_IMAGE"


def validate_product_id(value: object) -> RejectionReason | None:
    product_id = str(value).strip() if value is not None else ""
    if not product_id or not product_id.isdigit() or product_id.startswith("0"):
        return RejectionReason.INVALID_PRODUCT_ID
    return None

