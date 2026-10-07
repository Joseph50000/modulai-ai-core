import time
import json
import logging
from uuid import uuid4
from typing import Generator, Dict, Any, Optional

from src.nlp.schemas import NLPAnalyzeRequest, NLPAnalyzeResponse
from src.nlp.sensitive_words_detector import SensitiveWordsDetector
from src.nlp.sentiment_analyzer import SentimentAnalyzer
from src.nlp.summary_generator import SummaryGenerator
from src.nlp.hierarchical_classifier import HierarchicalClassifier
from src.nlp.urgency_evaluator import UrgencyEvaluator

logger = logging.getLogger(__name__)

class NLPService:
    """
    Orchestrateur unifié pour l'analyse NLP et la classification sémantique générique.
    Fournit les modes synchrone et streaming (SSE).
    """

    def __init__(self, llm_provider=None):
        if llm_provider is None:
            try:
                from src.providers.ollama_provider import OllamaProvider
                self.llm_provider = OllamaProvider()
            except Exception as e:
                logger.warning(f"Impossible d'initialiser OllamaProvider : {e}")
                self.llm_provider = None
        else:
            self.llm_provider = llm_provider

        self.sensitive_detector = SensitiveWordsDetector()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.summary_generator = SummaryGenerator()
        self.classifier = HierarchicalClassifier(llm_provider=self.llm_provider)
        self.urgency_evaluator = UrgencyEvaluator(llm_provider=self.llm_provider)

    def process(self, request: NLPAnalyzeRequest) -> NLPAnalyzeResponse:
        """
        Exécution synchrone complète du pipeline NLP.
        """
        start_time = time.time()
        correlation_id = request.correlation_id or str(uuid4())

        # 1. Détection des mots sensibles
        detected_keywords = self.sensitive_detector.detect(
            text=request.text,
            sensitive_keywords=request.sensitive_keywords
        )

        # 2. Analyse du sentiment et score de polarité
        sentiment, sentiment_score = self.sentiment_analyzer.analyze(text=request.text)

        # 3. Synthèse de texte
        summary = None
        if request.generate_summary:
            if request.summary_type == "abstractive" and request.enable_llm_reasoning and self.llm_provider:
                summary = self.summary_generator.generate_abstractive(
                    text=request.text,
                    llm_provider=self.llm_provider,
                    max_words=request.max_summary_words
                )
            else:
                summary = self.summary_generator.generate_extractive(
                    text=request.text,
                    max_words=request.max_summary_words
                )

        # 4. Évaluation de l'urgence / gravité
        provider_for_urgency = self.llm_provider if request.enable_llm_reasoning else None
        urgency_evaluator = UrgencyEvaluator(llm_provider=provider_for_urgency)
        urgency, urgency_reasoning = urgency_evaluator.evaluate(
            text=request.text,
            urgency_levels=request.urgency_levels,
            taxonomy=request.taxonomy,
            sensitive_keywords_detected=detected_keywords,
            sentiment=sentiment,
            context_nature=request.context_nature,
            context_definition=request.context_definition
        )

        # 5. Classification hiérarchique
        provider_for_classifier = self.llm_provider if request.enable_llm_reasoning else None
        classifier = HierarchicalClassifier(llm_provider=provider_for_classifier)
        category, subcategory, classification_reasoning = classifier.classify(
            text=request.text,
            taxonomy=request.taxonomy,
            context_nature=request.context_nature,
            context_definition=request.context_definition
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        return NLPAnalyzeResponse(
            status="success",
            urgency=urgency,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            sensitive_keywords_detected=detected_keywords,
            summary=summary,
            suggested_category=category,
            suggested_subcategory=subcategory,
            classification_reasoning=classification_reasoning,
            urgency_reasoning=urgency_reasoning,
            correlation_id=correlation_id,
            execution_time_ms=execution_time_ms
        )

    def process_stream(self, request: NLPAnalyzeRequest) -> Generator[Dict[str, Any], None, None]:
        """
        Exécution progressive sous forme de générateur pour flux Server-Sent Events (SSE).
        """
        correlation_id = request.correlation_id or str(uuid4())

        # Événement 0 : initialisation corrélation
        yield {"type": "correlation", "correlation_id": correlation_id}

        # Événement 1 : phase rapide locale (mots sensibles, sentiment, résumé extractif)
        detected_keywords = self.sensitive_detector.detect(
            text=request.text,
            sensitive_keywords=request.sensitive_keywords
        )
        sentiment, sentiment_score = self.sentiment_analyzer.analyze(text=request.text)
        summary = self.summary_generator.generate_extractive(
            text=request.text,
            max_words=request.max_summary_words
        ) if request.generate_summary else ""

        yield {
            "type": "init_base",
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "mots_cles_detectes": detected_keywords,
            "resume": summary,
            "correlation_id": correlation_id
        }

        # Événement 2 : calcul d'urgence
        provider_for_urgency = self.llm_provider if request.enable_llm_reasoning else None
        urgency_evaluator = UrgencyEvaluator(llm_provider=provider_for_urgency)
        urgency, urgency_reason = urgency_evaluator.evaluate(
            text=request.text,
            urgency_levels=request.urgency_levels,
            taxonomy=request.taxonomy,
            sensitive_keywords_detected=detected_keywords,
            sentiment=sentiment,
            context_nature=request.context_nature,
            context_definition=request.context_definition
        )

        yield {
            "type": "init_urgence",
            "urgence": urgency,
            "raisonnement_urgence": urgency_reason,
            "correlation_id": correlation_id
        }

        # Événement 3 : classification finale
        provider_for_classifier = self.llm_provider if request.enable_llm_reasoning else None
        classifier = HierarchicalClassifier(llm_provider=provider_for_classifier)
        category, subcategory, reasoning = classifier.classify(
            text=request.text,
            taxonomy=request.taxonomy,
            context_nature=request.context_nature,
            context_definition=request.context_definition
        )

        yield {
            "type": "final",
            "result": {
                "category": category,
                "subcategory": subcategory,
                "raisonnement": reasoning
            },
            "correlation_id": correlation_id
        }
