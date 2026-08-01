from handlers.palace.navigation import (
    _build_room_callback_data,
    _decode_room_callback_data,
    _decode_callback_part,
    _encode_callback_part,
)


def test_callback_parts_round_trip_long_and_special_names():
    raw = "Очень длинное название крыла " + "x" * 80 + " : / ?"
    encoded = _encode_callback_part(raw)
    assert _decode_callback_part(encoded) == raw


def test_room_callback_data_round_trips_wing_and_room():
    wing = "Крыло с пробелами"
    room = "Комната: с/двоеточием и вопросом?"
    data = _build_room_callback_data(wing, room)
    decoded_wing, decoded_room = _decode_room_callback_data(data)
    assert decoded_wing == wing
    assert decoded_room == room
