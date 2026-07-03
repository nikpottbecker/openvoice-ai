def test_phone_agent_imports() -> None:
    import phone_agent

    assert "agent" in phone_agent.__all__


def test_openvoice_namespace_imports() -> None:
    import openvoice_ai

    assert "core" in openvoice_ai.__all__
