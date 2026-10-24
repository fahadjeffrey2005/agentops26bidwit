import pytest
from pydantic import ValidationError

from bidwit.core.contracts import AuditEvent, PartError, Strict


class Box(Strict):
    name: str
    tags: tuple[str, ...] = ()


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        Box(name="a", sneaky=1)


def test_models_are_frozen():
    b = Box(name="a")
    with pytest.raises(ValidationError):
        b.name = "b"


def test_collections_are_immutable():
    assert isinstance(Box(name="a", tags=["x"]).tags, tuple)


def test_error_message_length_capped():
    with pytest.raises(ValidationError):
        PartError(kind="crash", type="X", message="m" * 501)


def test_audit_event_is_timezone_aware():
    assert AuditEvent(part="p", event="e").t.tzinfo is not None
