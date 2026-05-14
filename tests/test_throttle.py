from readless.throttle import StatusThrottle


def test_first_call_allowed():
    t = StatusThrottle(60, clock=lambda: 0.0)
    assert t.allow() is True


def test_second_call_within_interval_blocked():
    ticks = iter([0.0, 30.0])
    t = StatusThrottle(60, clock=lambda: next(ticks))
    assert t.allow() is True
    assert t.allow() is False


def test_call_after_interval_allowed():
    ticks = iter([0.0, 60.0])
    t = StatusThrottle(60, clock=lambda: next(ticks))
    assert t.allow() is True
    assert t.allow() is True


def test_blocked_call_does_not_reset_window():
    ticks = iter([0.0, 30.0, 61.0])
    t = StatusThrottle(60, clock=lambda: next(ticks))
    assert t.allow() is True
    assert t.allow() is False
    assert t.allow() is True
