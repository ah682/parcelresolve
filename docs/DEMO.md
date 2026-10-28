# Five-minute local walkthrough

Start `npm run dev` and open `http://127.0.0.1:8873`. The header must say **Local simulator**. No credentials, real labels, charges or messages are needed.

1. Select **1042 / Jamie Taylor**. The order is processing, £68.00 is captured, no label has been created, and warehouse truth is not dispatched. Review the cancellation/refund plan. **Approve** authorizes those exact actions; **Execute** performs them and verifies the refund and shipment allocation. The evidence tab includes each durable intent, receipt and read-back. The customer tab contains an unsent draft.
2. Select **1043 / Morgan Ellis**. ShipStation says Shipped while physical dispatch is unknown. The desk asks for warehouse evidence. **Confirm hold** creates an explicitly simulated acknowledgment. The new plan binds that acknowledgment and includes label void, cancellation and refund. Approve and execute to verify the post-label flow.
3. Select **1044 / Sam Rivera**. Confirm a hold, review the structured replacement address, approve and execute. Verify the old label is void, exactly one new label is active, and its tracking/address agree with commerce. The parcel is not automatically released from the hold.
4. Select **1045 / Robin Chen**. Investigate, approve and execute. The fixture loses the refund response after the refund succeeds. The case stays reconciling. **Reconcile & resume**, or a server restart, queries the original operation and verifies one refund without replaying it.
5. Select **1046 / Alex Brooks**. Confirm hold, approve and execute. The carrier refuses the void. The order remains under operator review; the desk does not claim a stopped/cancelled parcel or successful refund. **1047 / Casey James** shows why partially dispatched orders are similarly blocked.

For a recoverable partial failure, create a request on unused order **1048**. Try “Please help with this order” and clarify it to cancellation. In the **Lab**, select refund / before-write failure. Approve and execute: commerce is cancelled but the payment is visibly incomplete. Reconcile/resume finishes only the unwritten refund. A replacement-creation failure on an address case likewise preserves the voided old label and permits reconciliation of the approved remaining action.

To inspect hold recovery, use a freshly seeded **1043** before confirming its hold. Open **Lab**, select **Confirm warehouse hold** and the lost-response fault, then queue it. Confirm the hold: the receipt remains uncertain and the case asks for reconciliation. **Reconcile & resume** retrieves the same hold operation and verifies it; the separate warehouse history shows one operation, not a repeated hold. The current snapshot still shows the hold's actual expiry.

Switch to **Read only** to inspect evidence with mutation controls unavailable. Search the queue with `/`; move between detail tabs with arrow keys, Home and End. Use Escape to close a dialog and return focus. The footer names the configured interpreter, and the customer request names the interpretation that actually produced that case. Default deterministic rules make no model call. Inspect the customer draft without sending anything.

For repeatable browser acceptance without changing the running demo, run `npm test -- --browser-only`. It uses a disposable simulator and stores timestamped reports and desktop/mobile/failure screenshots under `frontend/qa`. Controlled-response presentation tests are labeled separately from real local API interactions.

Stop the server, run `make reset`, and restart to restore the six original cases plus the unused intake order. Reset is intentionally local and replaces this demo's history.
