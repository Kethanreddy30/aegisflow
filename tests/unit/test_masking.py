from masking.detector import detect
from masking.tokenizer import mask_text
from masking.reconstructor import reconstruct_sync


def test_masking_roundtrip_email():
    original = "Contact me at john@example.com"

    matches = detect(original)

    masked_text, token_map = mask_text(
        original,
        matches,
        tenant_id="tenant-a",
    )

    assert original != masked_text
    assert "__MASK_EMAIL_" in masked_text

    reconstructed = reconstruct_sync(
        masked_text,
        token_map,
    )

    assert reconstructed == original


def test_masking_is_deterministic():
    text = "john@example.com"

    matches = detect(text)

    masked_1, _ = mask_text(
        text,
        matches,
        tenant_id="tenant-a",
    )

    masked_2, _ = mask_text(
        text,
        matches,
        tenant_id="tenant-a",
    )

    assert masked_1 == masked_2


def test_masking_is_tenant_scoped():
    text = "john@example.com"

    matches = detect(text)

    masked_1, _ = mask_text(
        text,
        matches,
        tenant_id="tenant-a",
    )

    masked_2, _ = mask_text(
        text,
        matches,
        tenant_id="tenant-b",
    )

    assert masked_1 != masked_2
