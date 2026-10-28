"""Synthetic development demonstrations, independent of the evaluation corpus."""

from .domain import Address, Label, LineItem, Money, OrderSnapshot, Payment, Shipment, WarehouseAcknowledgment
from .engine import Engine


def make_order(
    order_id: str = "1042", *, labelled: bool = False, dispatched: bool = False, partial: bool = False
) -> OrderSnapshot:
    numeric_id = int(order_id) if order_id.isdigit() else sum(map(ord, order_id))
    address = Address(
        name="Jamie Taylor", line1="18 Alder Road", city="Bristol", postcode="BS1 4AB", country="GB"
    )
    lines = [
        LineItem(
            id="line-1",
            sku="LN-001",
            title="Linen everyday tote",
            quantity=2,
            unit_price=Money(minor=2400, currency="GBP"),
        ),
        LineItem(
            id="line-2",
            sku="CR-014",
            title="Ceramic travel cup",
            quantity=1,
            unit_price=Money(minor=2000, currency="GBP"),
        ),
    ]
    shipment = Shipment(
        id="shipment-" + order_id,
        order_key="wc-store-1-" + order_id,
        line_quantities={item.id: item.quantity for item in lines},
        status="shipped" if labelled else "awaiting_shipment",
    )
    labels = (
        [
            Label(
                id="label-" + order_id,
                shipment_id=shipment.id,
                status="active",
                tracking="RM" + str(numeric_id) + "GB",
                address=address,
            )
        ]
        if labelled
        else []
    )
    warehouse = WarehouseAcknowledgment(
        state="unknown" if labelled else "not_dispatched", reliable=not labelled
    )
    if dispatched or partial:
        warehouse = WarehouseAcknowledgment(
            state="partially_dispatched" if partial else "dispatched", reliable=True
        )
        for i, line in enumerate(lines):
            line.dispatched_quantity = 1 if partial and i == 0 else (0 if partial else line.quantity)
    return OrderSnapshot(
        id=order_id,
        woo_id=numeric_id,
        shipstation_order_id=90000 + numeric_id,
        shipstation_order_key=shipment.order_key,
        customer_name="Jamie Taylor",
        address=address,
        payment=Payment(captured=Money(minor=6800, currency="GBP")),
        lines=lines,
        labels=labels,
        shipments=[shipment],
        warehouse=warehouse,
        tracking=[item.tracking for item in labels],
    )


def seed_demo(engine: Engine) -> None:
    orders = {order.id: order for order in engine.sim.list_orders()}
    case_orders = {case["order_id"] for case in engine.store.list_cases()}
    names = ["Jamie Taylor", "Morgan Ellis", "Sam Rivera", "Robin Chen", "Alex Brooks", "Casey James"]
    for index, order_id in enumerate(["1042", "1043", "1044", "1045", "1046", "1047"]):
        order = orders.get(order_id)
        if order is None:
            order = make_order(order_id, labelled=index in {1, 2, 4, 5}, partial=index == 5)
            order.customer_name = names[index]
            order.address.name = names[index]
            engine.sim.put_order(order)
        if order_id in case_orders:
            continue
        if index in {3, 4}:
            kind, fault = ("refund", "lost_response") if index == 3 else ("void_label", "void_rejected")
            with engine.sim.connect() as conn:
                queued = conn.execute(
                    "SELECT 1 FROM faults WHERE order_id=? AND kind=? AND fault=?", (order_id, kind, fault)
                ).fetchone()
            # Queue before the case; an interrupted restart must neither lose nor rearm this fault.
            if queued is None:
                engine.sim.inject(order_id, kind, fault)
        if index == 2:
            target = order.address.model_copy(update={"line1": "27 Willow Lane", "postcode": "BS3 2EG"})
            case = engine.create_case(
                order_id,
                "I entered my old street. Please send this to 27 Willow Lane, Bristol, BS3 2EG.",
                intent="address",
                target_address=target,
            )
        else:
            case = engine.create_case(
                order_id, "Please cancel my entire order before it leaves the warehouse.", intent="cancel"
            )
        if index != 3:
            engine.investigate(case["id"])
    # Keep a clean, unused order available for the new-request workflow.
    if "1048" not in orders:
        order = make_order("1048")
        order.customer_name = "Drew Parker"
        engine.sim.put_order(order)
