"""
Complaint Agent — handles general complaints, exchange requests, and other intents.

Uses LLM to generate an empathetic, helpful response with order context.
Offers actionable next steps based on the complaint type.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agents.llm_gateway import call_llm, LLMGatewayError
from data.mock_db import order_lookup
from observability.logger import log_event


@dataclass
class ComplaintResult:
    draft_response: str
    action_taken: str = "complaint_logged"
    source_refs: list = field(default_factory=list)
    eligible: bool = False
    reason: str = ""


class ComplaintAgent:
    """
    Handles:
    - exchange_request  → product exchange / replacement
    - complaint         → general dissatisfaction, quality issues
    - other             → general queries not covered by other agents
    """

    SYSTEM_PROMPT = """You are a helpful, empathetic customer support agent for Cartly, an e-commerce platform.
A customer has a support request that is NOT a refund request — it may be an exchange request, a complaint, or a general question.

You have access to the customer's order details. Respond in a professional, friendly tone.

Rules:
- For exchange_request: offer a replacement/exchange, explain the process, set expectations
- For complaint: acknowledge empathetically, apologize sincerely, explain what you can do
- For other: answer helpfully using the order context

Always end with a clear next step (e.g., "Reply here to confirm you'd like an exchange" or "Contact us at support@cartly.in for further help").

Respond ONLY with valid JSON:
{
  "response": "<your customer-facing response, 2-4 sentences>",
  "action_taken": "<complaint_logged | exchange_initiated | info_provided>",
  "next_step": "<one clear action the customer should take next>"
}"""

    def resolve(
        self,
        ticket_id: str,
        order_id: str,
        intent: str,
        category: str,
        raw_ticket: str,
    ) -> ComplaintResult:
        t0 = time.monotonic()

        # Get order context
        order = order_lookup(order_id)
        order_ctx = ""
        if order:
            order_ctx = (
                f"Order #{order_id}: {order.get('product_name','N/A')} "
                f"| ₹{order.get('order_amount','N/A')} "
                f"| Status: {order.get('delivery_status','N/A')} "
                f"| Courier: {order.get('courier','N/A')}"
            )
        else:
            order_ctx = f"Order #{order_id}: not found in system"

        log_event(
            ticket_id,
            step="complaint_agent_lookup",
            latency_ms=(time.monotonic() - t0) * 1000,
            cost_tokens=0,
            decision=f"order_ctx_loaded — intent={intent}, category={category}",
            metadata={"order_id": order_id, "intent": intent, "category": category},
        )

        # LLM call
        t_llm = time.monotonic()
        user_msg = (
            f"Order context: {order_ctx}\n\n"
            f"Customer intent: {intent}\n"
            f"Category: {category}\n"
            f"Customer message: {raw_ticket}"
        )

        try:
            result, tokens, llm_lat = call_llm(
                self.SYSTEM_PROMPT,
                user_msg,
                expect_json=True,
            )

            response_text = result.get("response", "")
            action = result.get("action_taken", "complaint_logged")
            next_step = result.get("next_step", "")

            if next_step:
                draft = f"{response_text}\n\n**Next step:** {next_step}"
            else:
                draft = response_text

            log_event(
                ticket_id,
                step="complaint_agent_llm",
                latency_ms=(time.monotonic() - t_llm) * 1000,
                cost_tokens=tokens,
                decision=f"llm_ok — action={action}",
                metadata={"action_taken": action, "intent": intent},
            )

            return ComplaintResult(
                draft_response=draft,
                action_taken=action,
                source_refs=[],
                eligible=False,
                reason=f"Handled as {intent}: {category}",
            )

        except (LLMGatewayError, Exception) as exc:
            log_event(
                ticket_id,
                step="complaint_agent_llm",
                latency_ms=(time.monotonic() - t_llm) * 1000,
                cost_tokens=0,
                decision=f"llm_error — {str(exc)[:60]}",
                metadata={"error": str(exc)},
            )
            # Fallback: template response
            fallback = self._fallback_response(intent, order_id, order)
            return ComplaintResult(
                draft_response=fallback,
                action_taken="complaint_logged",
                source_refs=[],
                eligible=False,
                reason="LLM unavailable — fallback template used",
            )

    def _fallback_response(self, intent: str, order_id: str, order: dict | None) -> str:
        product = order.get("product_name", "your item") if order else "your item"
        if intent == "exchange_request":
            return (
                f"We've received your exchange request for **{product}** (#{order_id}). "
                f"Our team will review your request and reach out within 24 hours. "
                f"Please ensure the item is in its original packaging for a smooth exchange process."
            )
        elif intent == "complaint":
            return (
                f"We sincerely apologise for the inconvenience with your order **#{order_id}**. "
                f"Your complaint has been logged and our team will follow up within 24 hours. "
                f"If you'd like an immediate resolution, please describe the issue in detail."
            )
        else:
            return (
                f"Thank you for reaching out about order **#{order_id}**. "
                f"Our support team will assist you shortly. "
                f"For faster resolution, please email support@cartly.in with your order details."
            )
