import time
import logging
from typing import Dict, Any, List, Optional
from src.analytics.schemas import (
    AnalyticsQueryRequest,
    AnalyticsChartResponse,
    AnalyticsIntent
)
from src.analytics.nl_to_intent import NLToIntentEngine
from src.analytics.data_engine import DataEngine
from src.analytics.echarts_builder import EChartsBuilder

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Orchestrateur unifié pour le service Text-to-Viz & Analytics.
    Gère le cycle de bout en bout : Langage naturel ➔ Intention ➔ Données agrégées ➔ ECharts Option.
    """

    def __init__(self, llm_provider=None):
        self.intent_engine = NLToIntentEngine(llm_provider=llm_provider)
        self.data_engine = DataEngine()
        self.echarts_builder = EChartsBuilder()

    def process_query(self, request: AnalyticsQueryRequest) -> AnalyticsChartResponse:
        start_time = time.time()
        
        # 1. Inférence de l'intention analytique
        intent = self.intent_engine.infer_intent(
            query=request.query,
            schema=request.dataset_schema
        )

        # 2. Agrégation si des enregistrements sont fournis
        aggregated_data: List[Dict[str, Any]] = []
        if request.records:
            aggregated_data = self.data_engine.aggregate(
                records=request.records,
                intent=intent
            )

        # 3. Construction de l'option ECharts
        echarts_option = self.echarts_builder.build_option(
            aggregated_data=aggregated_data,
            intent=intent
        )

        # 4. Génération d'une synthèse (insight)
        insight = self._generate_insight(aggregated_data, intent)

        execution_time_ms = int((time.time() - start_time) * 1000)

        return AnalyticsChartResponse(
            status="success",
            intent=intent,
            echarts_option=echarts_option,
            aggregated_data=aggregated_data,
            summary_insight=insight,
            execution_time_ms=execution_time_ms,
            correlation_id=request.correlation_id
        )

    def _generate_insight(self, data: List[Dict[str, Any]], intent: AnalyticsIntent) -> Optional[str]:
        if not data:
            return "Aucune donnée disponible à analyser pour formuler un constat."

        metric_key = intent.metrics[0].alias if intent.metrics else "metric_value"
        metric_label = intent.metrics[0].label or "valeur"
        
        try:
            top_item = data[0]
            top_label = top_item.get("_group_label") or (top_item.get(intent.group_by[0]) if intent.group_by else "Total")
            top_val = top_item.get(metric_key, 0)
            
            total_val = sum(float(row.get(metric_key, 0)) for row in data)
            pct = (float(top_val) / total_val * 100) if total_val > 0 else 0

            if len(data) == 1:
                return f"Le niveau global de {metric_label} est de {top_val:,.1f}."
            
            return (
                f"Le segment le plus représenté est '{top_label}' avec {top_val:,.1f} "
                f"({pct:.1f}% de la valeur totale observée)."
            )
        except Exception as e:
            logger.debug(f"Erreur lors du calcul de l'insight: {e}")
            return None
