"""Deterministic hold-to-talk tests without a microphone or Windows API."""

from hermes_cli.voice_hold_to_talk import WindowsHoldToTalk, normalize_hold_key


def test_hold_keys_are_opt_in_and_limited_to_function_keys():
    assert normalize_hold_key(None) is None
    assert normalize_hold_key("ctrl+b") is None
    assert normalize_hold_key("f7") is None
    assert normalize_hold_key(" F8 ") == "f8"
    assert normalize_hold_key("f12") == "f12"


def test_press_hold_release_triggers_once():
    events = []
    controller = WindowsHoldToTalk(
        "f8",
        enabled=lambda: True,
        on_press=lambda: (events.append("start"), True)[1],
        on_release=lambda: events.append("send"),
    )
    for down in (False, True, True, True, False, False, True, False):
        controller.process_key_state(down)
    assert events == ["start", "send", "start", "send"]


def test_disabled_or_rejected_press_does_not_send():
    events = []
    enabled = False
    controller = WindowsHoldToTalk(
        "f8",
        enabled=lambda: enabled,
        on_press=lambda: (events.append("start"), False)[1],
        on_release=lambda: events.append("send"),
    )
    controller.process_key_state(True)
    controller.process_key_state(False)
    assert events == []
    enabled = True
    controller.process_key_state(True)
    controller.process_key_state(False)
    assert events == ["start"]


def test_press_exception_does_not_trigger_release():
    events = []
    def fail():
        events.append("failed")
        raise RuntimeError("audio unavailable")
    controller = WindowsHoldToTalk(
        "f9", enabled=lambda: True, on_press=fail,
        on_release=lambda: events.append("send"),
    )
    controller.process_key_state(True)
    controller.process_key_state(False)
    assert events == ["failed"]
