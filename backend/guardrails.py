"""Guardrail implementations for PII redaction, intent classification, input moderation, and hallucination detection."""

import re
import json
import logging
import asyncio
from typing import Dict, Any, Tuple, List, Optional
import httpx
from openai import AsyncOpenAI

from config import settings
from models import IntentResult, ModerationResult

logger = logging.getLogger(__name__)


class PIIDetector:
    """Detects and redacts Personally Identifiable Information (PII) from text."""

    PII_PATTERNS: Dict[str, str] = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b(\+91[\-\s]?)?[6-9]\d{9}\b|\b\+\d{1,3}[\s\-]?\d{6,14}\b",
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "in_pan": r"\b[A-Z]{5}\d{4}[A-Z]\b",
        "in_aadhaar": r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
        "in_vehicle": r"\b[A-Z]{2}[\s\-]?\d{2}[\s\-]?[A-Z]{1,2}[\s\-]?\d{4}\b",
    }

    REDACTION_MARKERS: Dict[str, str] = {
        "email": "[EMAIL_REDACTED]",
        "phone": "[PHONE_REDACTED]",
        "ip_address": "[IP_REDACTED]",
        "in_pan": "[PAN_REDACTED]",
        "in_aadhaar": "[AADHAAR_REDACTED]",
        "in_vehicle": "[VEHICLE_REDACTED]",
    }

    def detect_and_redact(self, value: Any) -> Tuple[str, bool, List[Dict[str, str]]]:
        """Detect and redact PII patterns from the input text.

        Args:
            value: The input text or object to scan.

        Returns:
            Tuple of (redacted_text, had_pii, list_of_pii_details).

        Examples:
            >>> detector = PIIDetector()
            >>> text, had_pii, details = detector.detect_and_redact("My email is test@example.com")
            >>> had_pii
            True
            >>> text
            'My email is [EMAIL_REDACTED]'
        """
        text: str = str(value)
        redacted_text: str = text
        pii_details: List[Dict[str, str]] = []

        for pii_type, pattern in self.PII_PATTERNS.items():
            matches: List[re.Match[str]] = list(re.finditer(pattern, text))
            if matches:
                for match in matches:
                    pii_details.append({
                        "pattern_name": pii_type,
                        "original_match": match.group()
                    })
                redacted_text = re.sub(pattern, self.REDACTION_MARKERS[pii_type], redacted_text)

        return redacted_text, bool(pii_details), pii_details


class IntentClassifier:
    """Classifies query intent into safety categories using deterministic pattern matching."""

    EMERGENCY_PATTERN: str = r"\b(i am|i'm|my|we are|we're|someone is|is having|help me|help|having a|experiencing)\b.*\b(heart attack|can't breathe|cannot breathe|suicide|overdose|choking|unconscious|bleeding heavily|chest pain|stroke|allergic reaction|anaphylaxis|poisoning)\b"

    DIAGNOSIS_PRESCRIPTION_KEYWORDS: List[str] = [
        "do i have", "what disease", "am i sick", "prescribe", "what medication",
        "dosage", "what drug should", "give me a prescription", "diagnose me"
    ]

    EMERGENCY_RESPONSE: str = (
        "IMMEDIATE ASSISTANCE REQUIRED: If you or someone around you is experiencing a medical emergency, "
        "please call your local emergency services (e.g., 911 or 112) or go to the nearest emergency room immediately."
    )

    DIAGNOSIS_REFUSAL_RESPONSE: str = (
        "I am an AI assistant and cannot diagnose medical conditions or prescribe medications. "
        "Please consult a qualified, licensed healthcare professional for medical diagnosis and personalized treatment options."
    )

    def classify(self, text: str) -> IntentResult:
        """Classify user query into emergency, diagnosis/prescription, or safe categories.

        Args:
            text: Query string to classify.

        Returns:
            IntentResult object containing category and optional response.

        Examples:
            >>> classifier = IntentClassifier()
            >>> res = classifier.classify("I am having chest pain")
            >>> res.category
            'emergency'
        """
        lower_text: str = text.lower()

        if re.search(self.EMERGENCY_PATTERN, lower_text):
            return IntentResult(category="emergency", response=self.EMERGENCY_RESPONSE)

        for kw in self.DIAGNOSIS_PRESCRIPTION_KEYWORDS:
            if kw in lower_text:
                return IntentResult(category="diagnosis", response=self.DIAGNOSIS_REFUSAL_RESPONSE)

        return IntentResult(category="safe", response=None)


class InputModerator:
    """Performs safety moderation checks against the external moderation API."""

    IGNORED_CATEGORIES: set[str] = {"health", "pii"}
    MODERATION_REFUSAL_RESPONSE: str = (
        "I cannot fulfill this request as the input violates safety policies."
    )

    async def check_moderation(self, text: str, session_id: str) -> ModerationResult:
        """Check input text against external moderation API using raw httpx POST.

        Args:
            text: Text to evaluate.
            session_id: Unique chat session ID for Portkey headers.

        Returns:
            ModerationResult describing blocked status and flagged categories.

        Examples:
            >>> moderator = InputModerator()
            >>> # async execution returns ModerationResult
        """
        if not settings.GUARDRAIL_BASE_URL or not settings.GUARDRAIL_API_KEY:
            logger.warning("Moderation base URL or API key not set. Skipping external moderation.")
            return ModerationResult(blocked=False)

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {settings.GUARDRAIL_API_KEY}",
            "Content-Type": "application/json",
            **settings.get_portkey_headers(session_id)
        }

        payload: Dict[str, Any] = {
            "model": settings.GUARDRAIL_MODEL_NAME,
            "input": text
        }

        url: str = f"{settings.GUARDRAIL_BASE_URL.rstrip('/')}/moderations"

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                results = data.get("results", [{}])[0]
                categories: Dict[str, bool] = results.get("categories", {})
                scores: Dict[str, float] = results.get("category_scores", {})

                flagged_categories: List[str] = [
                    cat for cat, is_flagged in categories.items()
                    if is_flagged and cat.lower() not in self.IGNORED_CATEGORIES
                ]

                blocked: bool = len(flagged_categories) > 0
                return ModerationResult(
                    blocked=blocked,
                    flagged_categories=flagged_categories,
                    category_scores=scores
                )

            except Exception as exc:
                if attempt < max_retries:
                    logger.warning(f"Moderation API request failed (attempt {attempt+1}): {exc}. Retrying...")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"Moderation API request failed after {max_retries} retries: {exc}. Failing CLOSED.")
                    return ModerationResult(blocked=True, flagged_categories=["system_error"], category_scores={"system_error": 1.0})


class HallucinationDetector:
    """Detects hallucinations in generated LLM responses using NLI LLM-as-a-Judge."""

    async def detect_hallucination(
        self, response_text: str, source_chunks: List[str], session_id: str
    ) -> bool:
        """Evaluate if response_text is factually supported by source_chunks.

        Args:
            response_text: The complete generated answer.
            source_chunks: Retrieved RAG context text passages.
            session_id: Unique chat session ID.

        Returns:
            True if hallucination detected, False if clean/supported.
        """
        if not response_text.strip():
            return False

        if not settings.JUDGE_BASE_URL or not settings.JUDGE_API_KEY:
            logger.warning("Judge LLM endpoint not configured. Skipping hallucination detection.")
            return False

        context_str: str = "\n---\n".join(source_chunks)
        client = AsyncOpenAI(
            base_url=settings.JUDGE_BASE_URL,
            api_key=settings.JUDGE_API_KEY,
            timeout=15.0
        )

        headers = settings.get_portkey_headers(session_id)

        prompt: str = (
            "You are a medical compliance auditor checking for dangerous, contradictory, or ungrounded medical claims.\n"
            "Evaluate if the Generated Text contains major unsupported medical claims or directly contradicts the Source Context.\n"
            "Note: General health guidance, standard medical disclaimers, markdown formatting, and conversational context are acceptable and should NOT be flagged.\n"
            "Respond ONLY with valid JSON: {\"is_hallucinated\": true} if the text contains dangerous or contradicting ungrounded claims, or {\"is_hallucinated\": false} if it is consistent and safe."
        )

        user_content: str = f"Source Context:\n{context_str}\n\nGenerated Text:\n{response_text}"

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                res = await client.chat.completions.create(
                    model=settings.JUDGE_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    user=session_id,
                    extra_headers=headers
                )

                raw_content: Optional[str] = res.choices[0].message.content
                if not raw_content:
                    return False

                parsed: Dict[str, Any] = json.loads(raw_content.strip())
                return bool(parsed.get("is_hallucinated", False))

            except Exception as exc:
                if attempt < max_retries:
                    logger.warning(f"Hallucination detection check failed (attempt {attempt+1}): {exc}. Retrying...")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"Hallucination detection check failed after {max_retries} retries: {exc}. Failing CLOSED.")
                    return True


pii_detector = PIIDetector()
intent_classifier = IntentClassifier()
input_moderator = InputModerator()
hallucination_detector = HallucinationDetector()
