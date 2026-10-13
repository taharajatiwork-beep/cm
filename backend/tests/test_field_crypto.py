from app.core.field_crypto import decrypt_secret, encrypt_secret, mask_iban


def test_encrypt_roundtrip():
    raw = "IR820120000000000000000000"
    stored = encrypt_secret(raw)
    assert stored.startswith("enc1:")
    assert decrypt_secret(stored) == raw


def test_mask_iban():
    assert "…" in mask_iban("IR820120000000000000000000")
