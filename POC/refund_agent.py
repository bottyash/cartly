"""
refund_agent.py
----------------
Refund Specialist Agent, per PDLC Stage 3 agent topology.

Single responsibility: check refund eligibility and, within the approved
threshold, draft the resolution. Two properties matter architecturally:

1. The INR 500 autonomy threshold is enforced with a plain Python `if`,
   BEFORE any LLM call. This is deliberate: a money-moving decision above
   the autonomy boundary must not depend on a model's behavior at all.
   It fires the same way every time, costs nothing, and cannot be
   prompt-injected around.

2. The agent only ever drafts within its eligibility finding -- it does
   not decide policy itself, it retrieves policy_kb evidence first and
   writes a draft that cites it. The Safety Critic re-checks those
   citations independently (see safety_critic.py).
"""

import mock_db
import policy_kb
import llm_client

REFUND_AUTONOMY_THRESHOLD_INR = 500.0


def check_eligibility(order, return_window_days_used: int = None) -> dict:
    """Pure, deterministic eligibility logic -- no LLM involved."""
    if not order.is_returnable:
        return {
            "eligible": False,
            "reason": "non_returnable_category",
            "policy_query": "non-returnable hygiene final sale",
        }

    days_elapsed = mock_db.days_since_order(order)
    if days_elapsed > order.return_window_days:
        return {
            "eligible": False,
            "reason": f"outside_return_window ({days_elapsed}d > {order.return_window_days}d)",
            "policy_query": "return window 30 days deadline",
        }

    return {
        "eligible": True,
        "reason": "within_window_and_returnable_category",
        "policy_query": "return window eligible refund",
    }


class RefundAgent:
    name = "refund_agent"

    def __init__(self, tracer):
        self.tracer = tracer

    def handle(self, ticket: dict) -> dict:
        """ticket: {ticket_id, order_id, customer_id, message, requested_amount}
        Returns a result dict the orchestrator uses to decide auto-resolve
        vs escalate, including the draft response and policy refs used.
        """
        ticket_id = ticket["ticket_id"]
        order_id = ticket["order_id"]

        order = mock_db.get_order(order_id)
        if order is None:
            self.tracer.log_step(ticket_id, self.name, "order_lookup_failed",
                                  {"order_id": order_id})
            return {
                "status": "escalate",
                "reason": "order_not_found",
                "draft_response": None,
                "policy_refs": [],
            }

        self.tracer.log_step(ticket_id, self.name, "order_lookup_ok", {
            "order_id": order.order_id, "amount_inr": order.amount_inr,
            "fulfilment_state": order.fulfilment_state,
        })

        # --- Deterministic threshold gate: fires before any LLM call ---
        if order.amount_inr > REFUND_AUTONOMY_THRESHOLD_INR:
            self.tracer.log_step(
                ticket_id, self.name, "deterministic_threshold_escalation",
                {"amount_inr": order.amount_inr,
                 "threshold_inr": REFUND_AUTONOMY_THRESHOLD_INR,
                 "note": "no LLM call made -- threshold check is a plain comparison"},
            )
            return {
                "status": "escalate",
                "reason": "above_autonomy_threshold",
                "draft_response": None,
                "policy_refs": policy_kb.retrieve("threshold 500 autonomous approval", category="refund"),
                "order": order,
            }

        # --- Eligibility check (deterministic) ---
        eligibility = check_eligibility(order)
        self.tracer.log_step(ticket_id, self.name, "eligibility_checked", eligibility)

        policy_refs = policy_kb.retrieve(eligibility["policy_query"], category="refund")
        self.tracer.log_step(ticket_id, self.name, "policy_retrieved",
                              {"refs": [p["source_id"] for p in policy_refs]})

        # --- Grounded drafting (LLM call, scoped to the eligibility finding) ---
        policy_text = "\n".join(f"[{p['source_id']}] {p['text']}" for p in policy_refs)
        if eligibility["eligible"]:
            instruction = (
                f"Draft a refund APPROVAL message for order {order.order_id}, "
                f"amount INR {order.amount_inr}. Cite the policy ID in brackets. "
                f"Retrieved policy context:\n{policy_text}"
            )
        else:
            instruction = (
                f"Draft a refund DECLINE message for order {order.order_id}. "
                f"Reason: {eligibility['reason']}. Cite the policy ID in brackets. "
                f"Retrieved policy context:\n{policy_text}"
            )

        text, tin, tout = llm_client.call_llm(
            system="You are Cartly's Refund Agent. Only state facts present in "
                   "the retrieved policy context. Always cite a policy ID.",
            prompt=instruction,
            model="claude-sonnet-4-6",
        )
        self.tracer.log_step(ticket_id, self.name, "draft_generated",
                              {"eligible": eligibility["eligible"]},
                              model="claude-sonnet-4-6", tokens_in=tin, tokens_out=tout)

        return {
            "status": "drafted",
            "eligible": eligibility["eligible"],
            "reason": eligibility["reason"],
            "draft_response": text,
            "policy_refs": policy_refs,
            "order": order,
        }
