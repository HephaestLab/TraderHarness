from decimal import Decimal

from traderharness.core.live_feed import LiveFeed


def test_live_feed_forwards_complete_frozen_web_event_protocol():
    feed = LiveFeed()
    event_types = [
        "run_start",
        "loading_data",
        "day_start",
        "phase_change",
        "committee_memo",
        "llm_response",
        "tool_call",
        "order_placed",
        "day_end",
        "run_end",
    ]

    for event_type in event_types:
        feed.event_bus.emit(event_type, marker=event_type)

    events = feed.drain()
    assert [event.type for event in events] == event_types
    assert [event.data["marker"] for event in events] == event_types


def test_live_feed_recursively_normalizes_decimal_and_dates_for_websocket_json():
    from datetime import date

    feed = LiveFeed()
    feed.push(
        "tool_call",
        nested={
            "price": Decimal("10.25"),
            "dates": [date(2024, 3, 4)],
        },
    )

    event = feed.get_nowait()
    assert event.data == {
        "nested": {
            "price": 10.25,
            "dates": ["2024-03-04"],
        }
    }
