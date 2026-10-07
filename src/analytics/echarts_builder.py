from typing import Dict, Any, List, Optional
from src.analytics.schemas import AnalyticsIntent

class EChartsBuilder:
    """
    Générateur universel de configurations d'options pour Apache ECharts.
    Prend les données agrégées et l'intention analytique pour générer l'objet JSON option complet.
    """

    COLOR_PALETTE = [
        "#6366F1", "#8B5CF6", "#EC4899", "#3B82F6",
        "#10B981", "#F59E0B", "#EF4444", "#14B8A6",
        "#64748B", "#06B6D4"
    ]

    def build_option(self, aggregated_data: List[Dict[str, Any]], intent: AnalyticsIntent) -> Dict[str, Any]:
        chart_type = intent.chart_type.lower()
        title_text = intent.title or "Visualisation Analytique"
        subtitle_text = intent.subtitle or f"Type: {chart_type.upper()}"

        base_option: Dict[str, Any] = {
            "title": {
                "text": title_text,
                "subtext": subtitle_text,
                "left": "center",
                "textStyle": {"fontSize": 16, "fontWeight": "bold", "color": "#1E293B"},
                "subtextStyle": {"fontSize": 12, "color": "#64748B"}
            },
            "color": self.COLOR_PALETTE,
            "animation": True,
            "animationDuration": 600
        }

        if not aggregated_data:
            base_option["graphic"] = {
                "type": "text",
                "left": "center",
                "top": "middle",
                "style": {
                    "text": "Aucune donnée disponible pour les critères sélectionnés.",
                    "fill": "#94A3B8",
                    "fontSize": 14
                }
            }
            return base_option

        if chart_type in ["pie", "doughnut"]:
            return self._build_pie_option(base_option, aggregated_data, intent, is_doughnut=(chart_type == "doughnut"))
        elif chart_type == "kpi":
            return self._build_kpi_option(base_option, aggregated_data, intent)
        elif chart_type in ["line", "area"]:
            return self._build_cartesian_option(base_option, aggregated_data, intent, is_line=True, is_area=(chart_type == "area"))
        elif chart_type == "stacked_bar":
            return self._build_cartesian_option(base_option, aggregated_data, intent, is_stacked=True)
        else: # default "bar"
            return self._build_cartesian_option(base_option, aggregated_data, intent)

    def _build_pie_option(
        self,
        base_option: Dict[str, Any],
        data: List[Dict[str, Any]],
        intent: AnalyticsIntent,
        is_doughnut: bool = False
    ) -> Dict[str, Any]:
        metric_key = intent.metrics[0].alias if intent.metrics else "metric_value"
        metric_label = intent.metrics[0].label or "Valeur" if intent.metrics else "Valeur"

        pie_items = []
        for row in data:
            name = str(row.get("_group_label") or (row.get(intent.group_by[0]) if intent.group_by else "Item"))
            val = row.get(metric_key, 0)
            pie_items.append({"name": name, "value": val})

        base_option["tooltip"] = {
            "trigger": "item",
            "formatter": "{a} <br/>{b} : {c} ({d}%)"
        }
        base_option["legend"] = {
            "orient": "horizontal",
            "bottom": "0%",
            "type": "scroll"
        }
        radius = ["40%", "70%"] if is_doughnut else "60%"
        base_option["series"] = [
            {
                "name": metric_label,
                "type": "pie",
                "radius": radius,
                "center": ["50%", "50%"],
                "data": pie_items,
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                },
                "label": {
                    "show": True,
                    "formatter": "{b}: {d}%"
                }
            }
        ]
        return base_option

    def _build_cartesian_option(
        self,
        base_option: Dict[str, Any],
        data: List[Dict[str, Any]],
        intent: AnalyticsIntent,
        is_line: bool = False,
        is_area: bool = False,
        is_stacked: bool = False
    ) -> Dict[str, Any]:
        categories = []
        for row in data:
            cat = str(row.get("_group_label") or (row.get(intent.group_by[0]) if intent.group_by else "Total"))
            categories.append(cat)

        base_option["tooltip"] = {
            "trigger": "axis",
            "axisPointer": {"type": "shadow" if not is_line else "line"}
        }
        base_option["grid"] = {
            "left": "3%",
            "right": "4%",
            "bottom": "12%",
            "top": "18%",
            "containLabel": True
        }
        base_option["xAxis"] = {
            "type": "category",
            "data": categories,
            "axisLabel": {
                "interval": 0,
                "rotate": 30 if len(categories) > 5 else 0,
                "color": "#475569"
            }
        }
        base_option["yAxis"] = {
            "type": "value",
            "axisLabel": {"color": "#475569"},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#E2E8F0"}}
        }

        series_list = []
        metrics = intent.metrics or []

        for m in metrics:
            series_data = [row.get(m.alias, 0) for row in data]
            s: Dict[str, Any] = {
                "name": m.label or m.alias,
                "type": "line" if is_line else "bar",
                "data": series_data,
            }
            if is_line:
                s["smooth"] = True
                if is_area:
                    s["areaStyle"] = {"opacity": 0.25}
            elif is_stacked:
                s["stack"] = "total"
            else:
                s["barMaxWidth"] = 40
                s["itemStyle"] = {"borderRadius": [4, 4, 0, 0]}

            series_list.append(s)

        base_option["series"] = series_list
        if len(series_list) > 1:
            base_option["legend"] = {
                "data": [s["name"] for s in series_list],
                "bottom": "0%"
            }

        return base_option

    def _build_kpi_option(
        self,
        base_option: Dict[str, Any],
        data: List[Dict[str, Any]],
        intent: AnalyticsIntent
    ) -> Dict[str, Any]:
        metric_key = intent.metrics[0].alias if intent.metrics else "metric_value"
        metric_label = intent.metrics[0].label or "Valeur" if intent.metrics else "Total"
        total_val = sum(float(row.get(metric_key, 0)) for row in data) if data else 0.0

        base_option["graphic"] = [
            {
                "type": "text",
                "left": "center",
                "top": "40%",
                "style": {
                    "text": f"{total_val:,.0f}".replace(",", " "),
                    "fill": "#4F46E5",
                    "fontSize": 48,
                    "fontWeight": "bold"
                }
            },
            {
                "type": "text",
                "left": "center",
                "top": "60%",
                "style": {
                    "text": metric_label,
                    "fill": "#64748B",
                    "fontSize": 16
                }
            }
        ]
        return base_option
