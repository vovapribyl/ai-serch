from product_search.corpus.rules import RejectionReason, validate_product_id


def test_accepts_digit_only_product_id_without_leading_zero() -> None:
    assert validate_product_id("12345") is None


def test_rejects_product_id_with_leading_zero_or_non_digits() -> None:
    assert validate_product_id("0123") is RejectionReason.INVALID_PRODUCT_ID
    assert validate_product_id("12-3") is RejectionReason.INVALID_PRODUCT_ID
    assert validate_product_id("") is RejectionReason.INVALID_PRODUCT_ID
