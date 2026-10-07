import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict
from src.analytics.schemas import AnalyticsIntent, FilterClause, MetricSpec

logger = logging.getLogger(__name__)

class DataEngine:
    """
    Moteur d'agrégation et de calcul tabulaire universel en mémoire.
    Applique filtres, regroupements multi-dimensions et fonctions d'agrégation.
    """

    @staticmethod
    def _matches_filter(row: Dict[str, Any], filter_clause: FilterClause) -> bool:
        field = filter_clause.field
        op = filter_clause.operator.lower()
        target_val = filter_clause.value
        row_val = row.get(field)

        if row_val is None:
            return False

        try:
            if op == "eq":
                return str(row_val).lower() == str(target_val).lower()
            elif op == "neq":
                return str(row_val).lower() != str(target_val).lower()
            elif op == "gt":
                return float(row_val) > float(target_val)
            elif op == "gte":
                return float(row_val) >= float(target_val)
            elif op == "lt":
                return float(row_val) < float(target_val)
            elif op == "lte":
                return float(row_val) <= float(target_val)
            elif op == "in":
                if isinstance(target_val, list):
                    return str(row_val).lower() in [str(v).lower() for v in target_val]
                return str(row_val).lower() in str(target_val).lower().split(",")
            elif op == "contains":
                return str(target_val).lower() in str(row_val).lower()
        except Exception:
            return False

        return True

    def filter_records(self, records: List[Dict[str, Any]], filters: List[FilterClause]) -> List[Dict[str, Any]]:
        if not filters:
            return records
        
        filtered = []
        for row in records:
            if all(self._matches_filter(row, f) for f in filters):
                filtered.append(row)
        return filtered

    def aggregate(self, records: List[Dict[str, Any]], intent: AnalyticsIntent) -> List[Dict[str, Any]]:
        """
        Effectue le filtrage, le regroupement et le calcul des métriques spécifiées dans l'intent.
        """
        if not records:
            return []

        # 1. Filtrage
        filtered_records = self.filter_records(records, intent.filters)
        if not filtered_records:
            return []

        group_fields = intent.group_by
        metrics = intent.metrics or [MetricSpec(operation="count", alias="metric_value")]

        # Si pas de dimension de groupement, agrégation globale (1 ligne)
        if not group_fields:
            aggregated_row: Dict[str, Any] = {"dimension": "Total"}
            for m in metrics:
                val = self._compute_metric(filtered_records, m)
                aggregated_row[m.alias] = val
            return [aggregated_row]

        # 2. Groupement par clé composite
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for row in filtered_records:
            key = tuple(str(row.get(f, "Non défini")) for f in group_fields)
            groups[key].append(row)

        results: List[Dict[str, Any]] = []
        for key_tuple, rows in groups.items():
            result_row: Dict[str, Any] = {}
            for i, f in enumerate(group_fields):
                result_row[f] = key_tuple[i]
            # Clé label lisible pour l'axe X ou les camemberts
            result_row["_group_label"] = " - ".join(key_tuple)

            for m in metrics:
                val = self._compute_metric(rows, m)
                result_row[m.alias] = val

            results.append(result_row)

        # 3. Tri
        sort_by = intent.sort_by or (metrics[0].alias if metrics else None)
        if sort_by:
            reverse = (intent.sort_order.lower() == "desc")
            def sort_key(item):
                val = item.get(sort_by)
                if val is None:
                    return float("-inf") if reverse else float("inf")
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return str(val)

            results.sort(key=sort_key, reverse=reverse)

        # 4. Limite
        if intent.limit and intent.limit > 0:
            results = results[:intent.limit]

        return results

    def _compute_metric(self, rows: List[Dict[str, Any]], metric: MetricSpec) -> float:
        op = metric.operation.lower()
        field = metric.field

        if op == "count" or not field:
            return float(len(rows))

        values = []
        for r in rows:
            v = r.get(field)
            if v is not None:
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    pass

        if not values:
            return 0.0

        if op == "sum":
            return round(sum(values), 2)
        elif op == "avg":
            return round(sum(values) / len(values), 2)
        elif op == "min":
            return round(min(values), 2)
        elif op == "max":
            return round(max(values), 2)

        return float(len(rows))
