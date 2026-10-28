"""Restart demo provisioning without replacing the operator's persisted work."""

import pytest

from parcelresolve.engine import Engine
from parcelresolve.seed import seed_demo


@pytest.mark.parametrize("boundary", ["order", "case", "fault"])
def test_interrupted_seed_resumes_without_duplicate_records(tmp_path, monkeypatch, boundary):
    engine = Engine(tmp_path)
    target, name = {
        "order": (engine.sim, "put_order"),
        "case": (engine, "create_case"),
        "fault": (engine.sim, "inject"),
    }[boundary]
    original = getattr(target, name)

    def interrupt(*args, **kwargs):
        result = original(*args, **kwargs)
        order_id = args[0].id if boundary == "order" else args[0]
        if order_id == ("1042" if boundary == "order" else "1045"):
            raise SystemExit("Interrupted demo provisioning")
        return result

    monkeypatch.setattr(target, name, interrupt)
    with pytest.raises(SystemExit, match="Interrupted demo"):
        seed_demo(engine)
    restarted = Engine(tmp_path)
    seed_demo(restarted)
    assert [order.id for order in restarted.sim.list_orders()] == [
        "1042",
        "1043",
        "1044",
        "1045",
        "1046",
        "1047",
        "1048",
    ]
    cases = restarted.store.list_cases()
    assert sorted(case["order_id"] for case in cases) == ["1042", "1043", "1044", "1045", "1046", "1047"]
    with restarted.sim.connect() as conn:
        faults = [tuple(row) for row in conn.execute("SELECT order_id,kind,fault FROM faults ORDER BY seq")]
    assert faults == [("1045", "refund", "lost_response"), ("1046", "void_label", "void_rejected")]


def test_repeat_seed_preserves_modified_and_resolved_records(tmp_path):
    engine = Engine(tmp_path)
    seed_demo(engine)
    case = next(case for case in engine.list_cases() if case["order_id"] == "1042")
    engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    assert engine.execute(case["id"])["status"] == "resolved"
    engine.sim.external_change("1043", "address")
    engine.sim.external_change("1048", "address")
    engine.create_case("1048", "Please review this separately", intent="unknown")
    before_cases = engine.list_cases()
    before_orders = engine.sim.list_orders()
    before_effects = engine.sim.effects("1042")
    seed_demo(Engine(tmp_path))
    assert engine.list_cases() == before_cases
    assert engine.sim.list_orders() == before_orders
    assert engine.sim.effects("1042") == before_effects
