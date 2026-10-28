import json
from pathlib import Path

from parcelresolve.engine import Engine
from parcelresolve.seed import make_order


def test_pre_label_cancellation_reaches_verified_terminal_state(tmp_path):
    fixture = json.loads((Path(__file__).parent / "fixtures/pre_label.json").read_text())
    engine = Engine(tmp_path)
    engine.sim.put_order(make_order(fixture["order_id"]))
    case = engine.create_case(fixture["order_id"], fixture["request"])
    case = engine.investigate(case["id"])
    assert case["status"] == "awaiting-approval"
    assert engine.sim.effects(fixture["order_id"]) == []
    case = engine.approve(case["id"], case["plan"]["hash"], case["plan"]["resource_version"])
    case = engine.execute(case["id"])
    assert case["status"] == fixture["expected"]["status"]
    order = engine.sim.read(fixture["order_id"])
    assert order.commercial_state == fixture["expected"]["commercial_state"]
    assert sum(r.amount.minor for r in order.payment.refunds) == fixture["expected"]["refunded_minor"]
    assert not any(label.status == "active" for label in order.labels)
    assert case["notification_status"] == "draft-only"
    assert all(a["provider_id"] for a in case["attempts"])
    assert any(e["kind"] == "read_back" for e in case["evidence"])
    assert Engine(tmp_path).view(case["id"])["status"] == "resolved"
