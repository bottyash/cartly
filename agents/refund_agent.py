"""
Refund Specialist Agent.

Responsibilities (per LLD §6.2):
  - Look up the order record (never reasons without data)
  - Retrieve applicable policy chunks (never asserts without a citation)
  - Produce an eligibility decision grounded in both
  - Abstain (force escalation) if no policy chunk found

Input:  order_id, refund_amount, reason (from Orchestrator)
Output: { eligible, action_taken, source_refs, transaction_ref, draft_response }
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from agents.llm_gateway import call_llm, LLMGatewayError
from data.mock_db import order_lookup
from data.policy_kb import policy_retrieval
from observability.logger import log_event


class RefundAgentResult:
    def __init__(
        self,
        eligible: bool,
        action_taken: str,
        source_refs: list[str],
        transaction_ref: str | None,
        draft_response: str,
        reason: str,
    ):
        self.eligible = eligible
        self.action_taken = action_taken
        self.source_refs = source_refs
        self.transaction_ref = transaction_ref
        self.draft_response = draft_response
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "action_taken": self.action_taken,
            "source_refs": self.source_refs,
            "transaction_ref": self.transaction_ref,
            "draft_response": self.draft_response,
            "reason": self.reason,
        }


class RefundAgent:

    SYSTEM_PROMPT = """You are a Refund Specialist Agent for an e-commerce marketplace.
You receive an order record and relevant policy text, and must determine refund eligibility.

CRITICAL PLATFORM CONSTRAINTS — YOU MUST FOLLOW THESE:
- ❌ NEVER ask the customer to send a photo, image, screenshot, or video of the product.
- ❌ NEVER request "visual proof", "a picture of the damage", or any image uploads.
- ❌ Cartly does NOT support image uploads — any such request will confuse and frustrate the customer.
- ✅ Base your decision on the order record, the customer's text description, and the policy text only.
- ✅ If more information is needed, ask for text-only details (e.g., "Can you describe the defect in more detail?").

RULES:
1. You may ONLY approve a refund if the policy text explicitly supports it.
2. You MUST cite the exact policy clause ID (e.g. POL-001) in your decision.
3. If the policy text does NOT support a refund, deny it and explain why using the policy.
4. Never invent policy rules that are not in the provided text.
5. Be concise and factual.
6. The draft_response must reference the specific policy basis for the decision so a quality reviewer
   can verify it (e.g. "Per our 30-day return policy (§3.1)..." or "As per our return policy...").
   Do NOT write vague responses that contradict the policy text.

You MUST respond with a JSON object with exactly these fields:
- eligible: true or false (boolean)
- action_taken: one of "refund_issued", "denied", or "replacement_offered" (string)
- source_refs: list of policy IDs you are citing, e.g. ["POL-001"] (array of strings)
- reason: one to two sentence explanation citing the policy clause (string)
- draft_response: the customer-facing message. Must be professional, empathetic, and consistent
  with the policy decision. If denied, briefly explain why per the policy. (string)

Example — approved:
{"eligible": true, "action_taken": "refund_issued", "source_refs": ["POL-001"], "reason": "Per POL-001, items that arrive broken or defective qualify for a full refund.", "draft_response": "We're sorry to hear your item arrived damaged! As per our damaged goods policy (§3.2), you are fully eligible for a refund. We have processed this for you and you should receive the amount within 3-5 business days."}

Example — denied (electronics, 31 days):
{"eligible": false, "action_taken": "denied", "source_refs": ["POL-003"], "reason": "Per POL-003, electronics may only be returned within 30 days of delivery. This order is outside the return window.", "draft_response": "We appreciate you reaching out! Unfortunately, per our electronics return policy (§5.4), returns for electronics can only be accepted within 30 days of delivery. As your order falls outside this window, we are unable to process a refund at this time. If the item is defective, please contact the manufacturer's warranty support."}"""

    def resolve(
        self,
        ticket_id: str,
        order_id: str,
        refund_amount: float,
        reason: str,
        category: str,
    ) -> RefundAgentResult:
        """
        Full resolution pipeline:
          1. order_lookup → abort if not found
          2. policy_retrieval → abstain if no chunks
          3. LLM eligibility reasoning with citation
        """

        # ── Step 1: Order lookup ──────────────────────────────────────────
        t0 = time.monotonic()
        order = order_lookup(order_id)
        lookup_latency = (time.monotonic() - t0) * 1000

        if order is None:
            log_event(
                ticket_id,
                step="refund_agent_order_lookup",
                latency_ms=lookup_latency,
                cost_tokens=0,
                decision="order_not_found",
                metadata={"order_id": order_id},
            )
            return RefundAgentResult(
                eligible=False,
                action_taken="denied",
                source_refs=[],
                transaction_ref=None,
                draft_response=(
                    f"We could not locate order #{order_id} in our system. "
                    "Please verify your order ID and contact support."
                ),
                reason=f"Order {order_id} not found in database.",
            )

        log_event(
            ticket_id,
            step="refund_agent_order_lookup",
            latency_ms=lookup_latency,
            cost_tokens=0,
            decision="order_found",
            metadata={
                "order_id": order_id,
                "product": order["product_name"],
                "amount": float(order["order_amount"]),
                "delivery_status": order["delivery_status"],
                "is_electronic": order["is_electronic"],
            },
        )

        # ── Step 2: Policy retrieval ──────────────────────────────────────
        t1 = time.monotonic()
        chunks = policy_retrieval(reason, category)
        policy_latency = (time.monotonic() - t1) * 1000

        if not chunks:
            log_event(
                ticket_id,
                step="refund_agent_policy_retrieval",
                latency_ms=policy_latency,
                cost_tokens=0,
                decision="no_policy_found — abstaining",
                metadata={"query": reason, "category": category},
            )
            # Abstain — never guess policy
            return RefundAgentResult(
                eligible=False,
                action_taken="abstained",
                source_refs=[],
                transaction_ref=None,
                draft_response=(
                    "We were unable to determine the applicable policy for your request. "
                    "A specialist will review your case and respond within 24 hours."
                ),
                reason="No matching policy found — abstaining to prevent ungrounded decision.",
            )

        log_event(
            ticket_id,
            step="refund_agent_policy_retrieval",
            latency_ms=policy_latency,
            cost_tokens=0,
            decision=f"found {len(chunks)} policy chunk(s)",
            metadata={"chunk_ids": [c["id"] for c in chunks]},
        )

        # ── Step 3: LLM eligibility reasoning ────────────────────────────
        policy_text = "\n\n".join(
            f"[{c['id']} — {c['clause']}]\n{c['text']}" for c in chunks
        )
        user_prompt = f"""CUSTOMER TICKET:
"{reason}"

ORDER RECORD:
- Order ID: {order['order_id']}
- Product: {order['product_name']} (category: {order['product_category']})
- Order Amount: ₹{order['order_amount']}
- Refund Claimed: ₹{refund_amount}
- Delivery Status: {order['delivery_status']}
- Is Electronic: {order['is_electronic']}
- Notes: {order.get('notes', 'N/A')}

APPLICABLE POLICY TEXT:
{policy_text}

Determine refund eligibility for this customer."""

        t2 = time.monotonic()
        try:
            result, tokens, llm_latency = call_llm(
                self.SYSTEM_PROMPT, user_prompt, expect_json=True
            )
        except LLMGatewayError as exc:
            log_event(
                ticket_id,
                step="refund_agent_llm",
                latency_ms=(time.monotonic() - t2) * 1000,
                cost_tokens=0,
                decision="llm_error — abstaining",
                metadata={"error": str(exc)},
            )
            return RefundAgentResult(
                eligible=False,
                action_taken="abstained",
                source_refs=[],
                transaction_ref=None,
                draft_response="A specialist will review your request shortly.",
                reason=f"LLM error: {str(exc)[:100]}",
            )

        eligible = bool(result.get("eligible", False))
        action_taken = result.get("action_taken", "denied")
        source_refs = result.get("source_refs", [c["id"] for c in chunks])
        llm_reason = result.get("reason", "")
        draft_response = result.get("draft_response", "")

        # Generate a mock transaction ref if refund is issued
        transaction_ref = f"TXN-{uuid.uuid4().hex[:10].upper()}" if eligible else None

        log_event(
            ticket_id,
            step="refund_agent_llm",
            latency_ms=(time.monotonic() - t2) * 1000,
            cost_tokens=tokens,
            decision=f"eligible={eligible}, action={action_taken}",
            metadata={
                "source_refs": source_refs,
                "transaction_ref": transaction_ref,
                "reason": llm_reason,
            },
        )

        return RefundAgentResult(
            eligible=eligible,
            action_taken=action_taken,
            source_refs=source_refs,
            transaction_ref=transaction_ref,
            draft_response=draft_response,
            reason=llm_reason,
        )
