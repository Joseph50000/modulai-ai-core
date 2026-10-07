import re
import json
import logging
from typing import Dict, Any, List, Optional
from src.analytics.schemas import (
    DatasetSchema,
    FieldDefinition,
    AnalyticsIntent,
    MetricSpec,
    FilterClause
)

logger = logging.getLogger(__name__)

class NLToIntentEngine:
    """
    Moteur d'inférence d'intention analytique à partir d'une question en langage naturel
    et d'un dictionnaire de données (DatasetSchema).
    Agnostique du domaine : aucune règle ni champ métier codé en dur.
    """

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        replacements = [('é', 'e'), ('è', 'e'), ('ê', 'e'), ('à', 'a'), ('ù', 'u'), ('ô', 'o'), ('î', 'i'), ('ç', 'c')]
        for a, b in replacements:
            text = text.replace(a, b)
        return text

    def infer_intent(self, query: str, schema: DatasetSchema, options: Optional[Dict[str, Any]] = None) -> AnalyticsIntent:
        """
        Déduit l'intention analytique. Tente d'abord le LLM si configuré,
        sinon applique une heuristique déterministe basée sur le schéma.
        """
        if self.llm_provider and hasattr(self.llm_provider, "generate"):
            try:
                llm_intent = self._infer_via_llm(query, schema, options)
                if llm_intent:
                    return llm_intent
            except Exception as e:
                logger.warning(f"Échec de l'inférence LLM pour l'intention analytique: {e}. Bascule sur l'heuristique.")

        return self._infer_heuristically(query, schema)

    def _infer_via_llm(self, query: str, schema: DatasetSchema, options: Optional[Dict[str, Any]] = None) -> Optional[AnalyticsIntent]:
        fields_desc = []
        for f in schema.fields:
            fields_desc.append(f"- {f.name} ({f.type}): {f.description or f.label or f.name}")
        schema_text = "\n".join(fields_desc) if fields_desc else "Aucun champ spécifié."

        system_prompt = (
            "Tu es un moteur d'analyse de données universel qui extrait l'intention de visualisation à partir d'une question.\n"
            "Voici les champs disponibles dans le dataset :\n"
            f"{schema_text}\n\n"
            "Règles strictes :\n"
            "Réponds UNIQUEMENT avec un objet JSON respectant cette structure exacte, sans aucun texte autour ni bloc markdown :\n"
            "{\n"
            '  "chart_type": "bar" | "line" | "pie" | "doughnut" | "area" | "stacked_bar" | "kpi",\n'
            '  "group_by": ["nom_colonne_dimension"],\n'
            '  "metrics": [{"field": "nom_colonne_ou_null", "operation": "count" | "sum" | "avg" | "min" | "max", "alias": "valeur", "label": "Libellé"}],\n'
            '  "filters": [{"field": "nom_colonne", "operator": "eq", "value": "valeur"}],\n'
            '  "sort_by": "valeur",\n'
            '  "sort_order": "desc" | "asc",\n'
            '  "limit": 10,\n'
            '  "title": "Titre clair et concis du graphique"\n'
            "}"
        )

        raw_output = self.llm_provider.generate(
            system_prompt=system_prompt,
            user_prompt=f"Question de l'utilisateur : \"{query}\"",
            options={"temperature": 0}
        )

        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            json_str = match.group(0)
            data = json.loads(json_str)
            # Validation des colonnes par rapport au schéma
            valid_field_names = {f.name.lower() for f in schema.fields}
            if valid_field_names:
                data["group_by"] = [col for col in data.get("group_by", []) if col.lower() in valid_field_names]

            return AnalyticsIntent(**data)
        return None

    def _infer_heuristically(self, query: str, schema: DatasetSchema) -> AnalyticsIntent:
        norm_query = self._normalize_text(query)
        fields = schema.fields

        # 1. Type de graphique
        chart_type = "bar"
        if any(w in norm_query for w in ["repartition", "part", "pourcentage", "distribution", "proportion"]):
            chart_type = "pie" if "doughnut" not in norm_query else "doughnut"
        elif any(w in norm_query for w in ["evolution", "tendance", "temps", "historique", "mensuel", "annuel", "chronologique"]):
            chart_type = "line"
        elif any(w in norm_query for w in ["cumul", "empile", "stack"]):
            chart_type = "stacked_bar"
        elif any(w in norm_query for w in ["indicateur", "total global", "kpi", "combien au total"]):
            chart_type = "kpi"

        # 2. Dimensions (group_by)
        group_by = []
        for f in fields:
            f_norm = self._normalize_text(f.name)
            label_norm = self._normalize_text(f.label or "")
            desc_norm = self._normalize_text(f.description or "")

            if f_norm in norm_query or (label_norm and label_norm in norm_query) or (desc_norm and desc_norm in norm_query):
                if f.type in ["string", "date", "boolean"] and f.name not in group_by:
                    group_by.append(f.name)

        # Si aucune dimension détectée, prendre le premier champ de type string ou date
        if not group_by and fields:
            for f in fields:
                if f.type in ["string", "date"]:
                    group_by.append(f.name)
                    break

        # 3. Métrique (Opération + Champ)
        operation = "count"
        target_metric_field = None
        metric_label = "Nombre"

        if any(w in norm_query for w in ["somme", "total", "montant", "volume", "chiffre"]):
            operation = "sum"
            metric_label = "Total"
        elif any(w in norm_query for w in ["moyenne", "moyen", "delai moyen", "duree moyenne", "prix moyen"]):
            operation = "avg"
            metric_label = "Moyenne"
        elif any(w in norm_query for w in ["minimum", "plus petit", "min"]):
            operation = "min"
            metric_label = "Minimum"
        elif any(w in norm_query for w in ["maximum", "plus grand", "max"]):
            operation = "max"
            metric_label = "Maximum"

        # Si l'opération nécessite un champ numérique (sum, avg, min, max)
        if operation in ["sum", "avg", "min", "max"]:
            numeric_fields = [f for f in fields if f.type in ["number", "float", "int", "integer"]]
            for nf in numeric_fields:
                nf_norm = self._normalize_text(nf.name)
                if nf_norm in norm_query or (nf.label and self._normalize_text(nf.label) in norm_query):
                    target_metric_field = nf.name
                    metric_label = f"{metric_label} ({nf.label or nf.name})"
                    break
            if not target_metric_field and numeric_fields:
                target_metric_field = numeric_fields[0].name
                metric_label = f"{metric_label} ({numeric_fields[0].label or numeric_fields[0].name})"
            elif not target_metric_field:
                # Pas de champ numérique disponible, repli sur count
                operation = "count"
                metric_label = "Nombre"

        metrics = [
            MetricSpec(
                field=target_metric_field,
                operation=operation,
                alias="metric_value",
                label=metric_label
            )
        ]

        # 4. Filtres simples heuristiques
        filters: List[FilterClause] = []
        for f in fields:
            if f.type == "string":
                # Recherche d'expressions du type "statut résolu" ou "type bug"
                match_val = re.search(rf"\b{re.escape(f.name)}\s*[:=]\s*([a-zA-Z0-9_\-]+)", query, re.IGNORECASE)
                if match_val:
                    filters.append(FilterClause(field=f.name, operator="eq", value=match_val.group(1)))

        # 5. Titre
        dim_str = ", ".join(group_by) if group_by else "ensemble des données"
        title = f"{metric_label} par {dim_str}"

        return AnalyticsIntent(
            chart_type=chart_type,
            group_by=group_by[:2],
            metrics=metrics,
            filters=filters,
            sort_by="metric_value",
            sort_order="desc",
            limit=10,
            title=title
        )
