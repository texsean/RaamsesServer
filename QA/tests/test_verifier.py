from QA.emulator.verifier_emulator import verify_agent


def test_local_llm_verification():
    result = verify_agent("agent-001", "LocalLLM")
    assert result["methodology_used"] == "LocalLLM"
    assert result["verified"] is True


def test_filebased_verification():
    result = verify_agent("agent-002", "FILEbased")
    assert result["methodology_used"] == "FILEbased"


def test_auto_fallback():
    result = verify_agent("agent-003", "auto")
    assert result["confidence"] > 0.8
