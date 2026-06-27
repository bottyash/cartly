"""
orchestrator.py
-----------------
Orchestrator Agent: the outer loop, per the orchestration decision record
(PDLC 3.3). Implements router-and-handoff at the entry point (triage),
orchestrator-worker as the outer loop (this class delegating to
RefundAgent), and the evaluator-optimizer final gate (SafetyCritic) before
any response is finalized.

POC scope: refund-eligibility tickets only. Triage here is a lightweight
keyword classifier (cheap-tier behavior) rather than an LLM call, which
matches the architecture's cost-tier reasoning -- triage is high-volume
and should be near-zero cost. A real Tier 1 build would extend this with
an order-status/WISMO path and other specialists registered the same way.
"""

import refund_agent
import safety_critic
import observability

REFUND_KEYWORDS = {"refund", "return", "money back", "reimburse"}


class Orchestrator:
    def __init__(self):
        self.tracer = observability.TraceLogger()
        self.refund_agent = refund_agent.RefundAgent(self.tracer)
        self.safety_critic = safety_critic.SafetyCritic(self.tracer)

    def triage(self, ticket: dict) -> str:
        text = ticket["message"].lower()
        intent = "refund_request" if any(k in text for k in REFUND_KEYWORDS) else "unclassified"
        self.tracer.log_step(ticket["ticket_id"], "triage_agent", "intent_classified",
                              {"intent": intent})
        return intent

    def process_ticket(self, ticket: dict) -> dict:
        ticket_id = ticket["ticket_id"]
        self.tracer.log_step(ticket_id, "orchestrator", "ticket_received",
                              {"order_id": ticket.get("order_id"), "message": ticket["message"]})

        intent = self.triage(ticket)
        if intent != "refund_request":
            self.tracer.log_step(ticket_id, "orchestrator", "out_of_poc_scope", {"intent": intent})
            return self._escalate(ticket, reason="intent_outside_poc_scope")

        result = self.refund_agent.handle(ticket)

        if result["status"] == "escalate":
            return self._escalate(ticket, reason=result["reason"], refund_result=result)

        # result["status"] == "drafted" -> run through the Safety Critic gate
        verdict = self.safety_critic.review(ticket_id, ticket["message"], result)

        if not verdict["approved"]:
            self.tracer.log_step(ticket_id, "orchestrator", "critic_blocked_response",
                                  {"flags": verdict["flags"]})
            return self._escalate(ticket, reason="safety_critic_block",
                                   refund_result=result, critic_verdict=verdict)

        self.tracer.log_step(ticket_id, "orchestrator", "auto_resolved",
                              {"eligible": result["eligible"]})
        return {
            "outcome": "auto_resolved",
            "ticket_id": ticket_id,
            "response_to_customer": result["draft_response"],
            "eligible": result["eligible"],
            "policy_refs": [r["source_id"] for r in result["policy_refs"]],
            "faithfulness_score": verdict["faithfulness_score"],
            "cost_inr": self.tracer.ticket_cost(ticket_id),
        }

    def _escalate(self, ticket, reason, refund_result=None, critic_verdict=None) -> dict:
        ticket_id = ticket["ticket_id"]
        case_brief = {
            "ticket_id": ticket_id,
            "order_id": ticket.get("order_id"),
            "customer_message": ticket["message"],
            "escalation_reason": reason,
            "what_was_attempted": [e["action"] for e in self.tracer.get_trace(ticket_id)],
        }
        if refund_result:
            case_brief["eligibility_finding"] = refund_result.get("reason")
            case_brief["draft_on_file"] = refund_result.get("draft_response")
        if critic_verdict:
            case_brief["safety_flags"] = critic_verdict.get("flags")

        self.tracer.log_step(ticket_id, "escalation_agent", "case_brief_built",
                              {"reason": reason})

        return {
            "outcome": "escalated",
            "ticket_id": ticket_id,
            "escalation_reason": reason,
            "case_brief": case_brief,
            "cost_inr": self.tracer.ticket_cost(ticket_id),
        }
