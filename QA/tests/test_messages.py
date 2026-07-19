import pytest
from src.linux.rgs.messages.envelope import RaamsesMessage, Header
from src.linux.rgs.messages.register import Register


def test_header_has_schema_version():
    h = Header(device_id="test-uuid", schema_version="1.0")
    assert h.schema_version == "1.0"


def test_register_message_contains_schema():
    reg = Register(device_id="abc", schema_version="1.1", device_type="cyd")
    assert reg.schema_version == "1.1"
