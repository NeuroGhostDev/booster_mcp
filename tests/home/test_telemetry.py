from booster_home.telemetry.events import validate_event


def test_telemetry_redacts_secret_and_validates_envelope() -> None:
    event = validate_event(
        {
            "type": "MODEL_REQUEST",
            "session_id": "s",
            "request_id": "r",
            "payload": {"text": "Authorization: Bearer secret-value"},
        }
    )
    assert "secret-value" not in str(event.payload)
    assert "[REDACTED]" in event.payload["text"]


def test_telemetry_redacts_nested_secret_values() -> None:
    event = validate_event(
        {
            "type": "MODEL_RESPONSE",
            "session_id": "s",
            "request_id": "r",
            "payload": {
                "nested": {"token": "nested-secret"},
                "items": [{"api_key": "list-secret"}],
            },
        }
    )

    assert "nested-secret" not in str(event.payload)
    assert "list-secret" not in str(event.payload)
