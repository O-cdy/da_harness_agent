from harness.core.contracts.redaction import REDACTED, redact, safe_exception, safe_repr


def test_redacts_nested_dict_list_and_string_values() -> None:
    value = {
        "result": [
            {"phone": "+1 555 123 4567"},
            "contact alice@example.com",
            {"count": 2},
        ]
    }

    redacted = redact(value)
    assert redacted["result"][0]["phone"] == REDACTED
    assert redacted["result"][1] == f"contact {REDACTED}"
    assert redacted["result"][2]["count"] == 2


def test_repr_and_exception_never_expose_sensitive_canaries() -> None:
    represented = safe_repr({"dsn": "mysql://user:pass@host/db", "rows": 1})
    exception = safe_exception(ValueError("buyer_name: Ada Lovelace"))
    spaced_secret = safe_exception(ValueError("password: multi word secret"))

    assert "mysql://" not in represented
    assert "Ada Lovelace" not in exception
    assert "multi" not in spaced_secret
    assert "word" not in spaced_secret
    assert REDACTED in represented
    assert REDACTED in exception


def test_unknown_objects_and_bytes_are_reduced_to_safe_summaries() -> None:
    class Canary:
        def __repr__(self) -> str:
            return "token=hidden"

    assert redact(b"raw-secret") == REDACTED
    assert redact(Canary()) == REDACTED
    assert redact(None) is None
