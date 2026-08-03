import pytest

from planeops.secrets import RedactionError, SecretsHandle, materialization_handle


class FakeBackend:
    name = "fake"

    def __init__(self):
        self.get_calls = []

    def exists(self, name):
        return name == "present"

    def meta(self, name):
        return {"configured": True} if name == "present" else None

    def get(self, name):
        self.get_calls.append(name)
        return f"value-of-{name}"


def test_presence_handle_allows_presence_but_not_value():
    b = FakeBackend()
    h = SecretsHandle(b)
    assert h.exists("present") is True
    assert h.meta("present") == {"configured": True}
    with pytest.raises(RedactionError):
        h.get("present")
    assert b.get_calls == []  # never decrypted


def test_presence_handle_exposes_no_value_escape_hatch():
    # no method on the handle an adapter holds may yield a value or a
    # value-capable handle; any escape hatch would make the seal a convention
    # instead of a guarantee.
    h = SecretsHandle(FakeBackend())
    assert not hasattr(h, "unsealed")
    assert not hasattr(h, "sealed")


def test_materialization_handle_permits_get():
    b = FakeBackend()
    h = materialization_handle(b)
    assert h.get("present") == "value-of-present"
    assert b.get_calls == ["present"]


def test_a_presence_handle_cannot_be_escalated_to_a_value_handle():
    # Wrapping a presence handle (what an adapter has) does not grant a value:
    # its get() still raises, because the underlying "backend" is the gate itself.
    presence = SecretsHandle(FakeBackend())
    with pytest.raises(RedactionError):
        materialization_handle(presence).get("present")
