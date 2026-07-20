"""
Product Inquiry Agent — answers generic questions about products and policies
WITHOUT requiring an order ID.

Handles queries like:
  - "Is the SoundMax Pro returnable?"
  - "What is the return policy for electronics?"
  - "How long does shipping take?"
  - "Can I exchange a kurta for a different size?"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agents.llm_gateway import call_llm, LLMGatewayError
from data.policy_kb import policy_retrieval
from data.products import search_products


@dataclass
class ProductInquiryResult:
    draft_response: str
    action_taken: str = "info_provided"
    source_refs: list = field(default_factory=list)


class ProductInquiryAgent:
    """
    Answers product and policy questions without needing an order ID.
    Retrieves relevant policy chunks + product data, then uses LLM.
    """

    SYSTEM_PROMPT = """You are Cartly's helpful AI shopping assistant. You help customers with ALL kinds of questions about Cartly — shopping, product recommendations, policies, orders, shipping, returns, and more.

You have access to the product catalog and company policy documents as context.

CRITICAL PLATFORM CONSTRAINTS — YOU MUST FOLLOW THESE:
- ❌ NEVER ask the customer to provide a photo, image, screenshot, or video.
- ❌ Cartly does NOT support image uploads of any kind.
- ✅ Base all answers on the customer's text description and the available catalog/policy context.

Your role:
- PRODUCT RECOMMENDATIONS: When a customer wants to buy something, suggest suitable products from the catalog based on their needs. Highlight features, price, and value.
- POLICY QUESTIONS: Answer questions about return, exchange, warranty, shipping, and payment policies accurately using the provided policy context.
- SHOPPING GUIDANCE: Help customers decide between products, understand features, or find the right item.
- GENERAL HELP: Answer any e-commerce question a shopper might have — "Can I track my order?", "What payment methods do you accept?", "How do I contact support?", etc.

Important rules:
- Be friendly, helpful, and conversational — like a knowledgeable store assistant.
- Do NOT default to talking about refunds unless the customer specifically asks about returns/refunds.
- If recommending products, mention 2-3 options when available with their prices and key features.
- For policy questions, quote exact timelines and conditions from the policy documents.
- If you don't have enough context to answer, be honest and say so, then suggest contacting support@cartly.in.
- End responses with a helpful offer to assist further.

Respond ONLY with valid JSON:
{
  "response": "<your helpful answer, 2-6 sentences, friendly and informative>",
  "source_refs": ["<policy clause or product id if cited, else empty>"],
  "confidence": <float 0.0-1.0>
}"""

    def resolve(self, ticket_id: str, raw_query: str) -> ProductInquiryResult:
        from observability.logger import log_event

        t0 = time.monotonic()

        # Retrieve relevant products
        matched_products = search_products(raw_query)[:3]

        # Retrieve relevant policy chunks
        policy_chunks = policy_retrieval(raw_query, category=None)

        # Build context
        product_ctx = ""
        if matched_products:
            lines = []
            for p in matched_products:
                lines.append(
                    f"Product ID: {p['id']} | Name: {p['name']} | Category: {p['category']} | "
                    f"Price: ₹{p['price']} | In Stock: {'Yes' if p['in_stock'] else 'No'} | "
                    f"Rating: {p['rating']}/5 | Description: {p['description']} | "
                    f"Returnable: {'Yes' if p['is_returnable'] else 'No — electronics policy'} | "
                    f"Return window: {p['return_window_days']} days | "
                    f"Warranty: {p['warranty_months']} months"
                )
            product_ctx = "AVAILABLE PRODUCTS:\n" + "\n".join(lines)

        policy_ctx = ""
        if policy_chunks:
            lines = []
            for chunk in policy_chunks:
                lines.append(f"[{chunk['clause']}] {chunk['title']}: {chunk['text']}")
            policy_ctx = "RELEVANT POLICIES:\n" + "\n\n".join(lines)

        context = "\n\n".join(filter(None, [product_ctx, policy_ctx]))

        log_event(
            ticket_id,
            step="product_agent_retrieval",
            latency_ms=(time.monotonic() - t0) * 1000,
            cost_tokens=0,
            decision=f"found {len(matched_products)} products, {len(policy_chunks)} policy chunks",
            metadata={"products": [p["id"] for p in matched_products], "policies": [c["id"] for c in policy_chunks]},
        )

        # LLM call
        t_llm = time.monotonic()
        user_msg = f"{context}\n\nCustomer question: {raw_query}"

        try:
            result, tokens, _ = call_llm(self.SYSTEM_PROMPT, user_msg, expect_json=True)

            response_text = result.get("response", "")
            source_refs = result.get("source_refs", [])

            log_event(
                ticket_id,
                step="product_agent_llm",
                latency_ms=(time.monotonic() - t_llm) * 1000,
                cost_tokens=tokens,
                decision="llm_ok",
                metadata={"source_refs": source_refs},
            )

            return ProductInquiryResult(
                draft_response=response_text or self._fallback(raw_query, matched_products, policy_chunks),
                action_taken="info_provided",
                source_refs=source_refs,
            )

        except (LLMGatewayError, Exception) as exc:
            log_event(
                ticket_id,
                step="product_agent_llm",
                latency_ms=(time.monotonic() - t_llm) * 1000,
                cost_tokens=0,
                decision=f"llm_error — {str(exc)[:60]}",
                metadata={"error": str(exc)},
            )
            return ProductInquiryResult(
                draft_response=self._fallback(raw_query, matched_products, policy_chunks),
                action_taken="info_provided",
                source_refs=[],
            )

    def _fallback(self, query: str, products: list, policies: list) -> str:
        parts = []
        if products:
            p = products[0]
            ret_status = "✅ Returnable" if p["is_returnable"] else "❌ Non-Returnable"
            parts.append(
                f"**{p['name']}** — {ret_status}\n"
                f"Return window: {p['return_window_days']} days | {p['return_condition']}"
            )
        if policies:
            parts.append(f"\n📋 **Policy:** {policies[0]['title']}\n_{policies[0]['clause']}_")
        if not parts:
            parts.append(
                "I couldn't find specific information for your query. "
                "Please contact support@cartly.in for detailed assistance."
            )
        return "\n".join(parts)
