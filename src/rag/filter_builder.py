from typing import Dict, Any, Optional, List

class FilterBuilder:
    """
    Constructeur et normalisateur de filtres de métadonnées pour ChromaDB.
    Transforme des filtres multi-critères standards en clauses ChromaDB valides ($and, $or, $in, $eq).
    """

    @staticmethod
    def build(raw_filter: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not raw_filter or not isinstance(raw_filter, dict):
            return None

        # Si le filtre contient déjà uniquement un opérateur logique racine valide ($and, $or)
        if len(raw_filter) == 1 and ("$and" in raw_filter or "$or" in raw_filter):
            op = "$and" if "$and" in raw_filter else "$or"
            items = raw_filter[op]
            if isinstance(items, list):
                built_items = [FilterBuilder.build(item) for item in items if FilterBuilder.build(item)]
                if len(built_items) > 1:
                    return {op: built_items}
                elif len(built_items) == 1:
                    return built_items[0]
                return None

        conditions: List[Dict[str, Any]] = []

        for key, val in raw_filter.items():
            if key in ["$and", "$or"]:
                if isinstance(val, list):
                    built_sub = [FilterBuilder.build(sub) for sub in val if FilterBuilder.build(sub)]
                    if len(built_sub) > 1:
                        conditions.append({key: built_sub})
                    elif len(built_sub) == 1:
                        conditions.append(built_sub[0])
                continue

            # Si la valeur est une liste brute (ex: {"type": ["A", "B"]}), convertir en $in
            if isinstance(val, list):
                conditions.append({key: {"$in": val}})
            elif isinstance(val, dict):
                # Si c'est déjà un dict d'opérateur ChromaDB (ex: {"$gt": 10}, {"$in": [...]})
                conditions.append({key: val})
            else:
                # Valeur scalaire simple
                conditions.append({key: val})

        if not conditions:
            return None
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}
