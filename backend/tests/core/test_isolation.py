from bidwit.core.contracts import Strict
from bidwit.core.isolation import run_part


class Out(Strict):
    n: int


def good(x):
    return Out(n=x)


def crashes(x):
    raise RuntimeError("boom " + "z" * 2000)


def wrong_type(x):
    return {"n": "not a number"}


def test_ok():
    res, ev = run_part("demo", good, 3, Out)
    assert res.ok and res.value == Out(n=3) and res.error is None and ev.level == "info"


def test_crash_is_contained_not_raised():
    res, ev = run_part("demo", crashes, 1, Out)
    assert not res.ok and res.value is None
    assert res.error.kind == "crash" and res.error.type == "RuntimeError"
    assert len(res.error.message) <= 500 and "\n" not in res.error.message
    assert ev.level == "error"


def test_wrong_output_type_is_caught():
    res, _ = run_part("demo", wrong_type, 1, Out)
    assert not res.ok and res.error.kind == "bad_output"


def test_bad_input_is_reported_as_bad_input():
    res, _ = run_part("demo", lambda x: Out(n=x), "abc", Out)
    assert not res.ok and res.error.kind == "bad_input"


def test_keyboard_interrupt_is_not_swallowed():
    import pytest

    def stop(_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_part("demo", stop, 1, Out)


def test_list_outputs_validate_each_item():
    res, _ = run_part("demo", lambda x: [Out(n=1), {"n": "x"}], 0, list[Out])
    assert not res.ok and res.error.kind == "bad_output"


def test_bad_part_name_does_not_raise():
    res, ev = run_part("x" * 100, good, 1, Out)
    assert res.ok and len(res.part) == 40
    res, _ = run_part("", good, 1, Out)
    assert res.part == "unknown"


def test_rejected_is_its_own_kind():
    from bidwit.core.contracts import Rejected

    def refuse(_):
        raise Rejected("file is encrypted")

    res, ev = run_part("demo", refuse, 1, Out)
    assert not res.ok and res.error.kind == "rejected" and res.error.message == "file is encrypted"
