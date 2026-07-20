import pytest

from phone_agent.dashboard.app import menu_config_json, validate_menu_config_json


def test_default_menu_json_is_valid() -> None:
    validate_menu_config_json(menu_config_json(default=True))


def test_menu_json_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate key"):
        validate_menu_config_json(
            """
            {
              "items": [
                {"key": "1", "action": "CREATE_APPOINTMENT", "label": "Termin"},
                {"key": "1", "action": "REQUEST_CALLBACK", "label": "Rueckruf"}
              ]
            }
            """
        )


def test_menu_json_rejects_invalid_action() -> None:
    with pytest.raises(ValueError, match="invalid action"):
        validate_menu_config_json(
            """
            {
              "items": [
                {"key": "1", "action": "DOES_NOT_EXIST", "label": "Kaputt"}
              ]
            }
            """
        )
