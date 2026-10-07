from typing import Any, Dict, List, Optional


def apply_diarization(
    segments: List[Dict[str, Any]],
    speaker_roles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Normalise les identifiants de locuteurs et applique les rôles configurés."""
    if not segments:
        return {"segments": [], "speakers": [], "status": "EMPTY"}

    speaker_map: Dict[str, str] = {}
    normalized_segments: List[Dict[str, Any]] = []

    # Construire la liste des rôles cibles ordonnés
    roles = speaker_roles or []

    for seg in segments:
        raw_speaker = seg.get("speaker")
        if not raw_speaker or not str(raw_speaker).strip():
            # Locuteur non identifié pour ce segment
            normalized_segments.append(dict(seg))
            continue

        raw_key = str(raw_speaker).strip()
        if raw_key not in speaker_map:
            idx = len(speaker_map)
            if idx < len(roles) and roles[idx]:
                speaker_map[raw_key] = roles[idx].strip()
            else:
                speaker_map[raw_key] = f"SPEAKER_{idx:02d}"

        updated_seg = dict(seg)
        updated_seg["speaker"] = speaker_map[raw_key]
        normalized_segments.append(updated_seg)

    speakers = sorted(set(speaker_map.values()))
    status = "APPLIED" if speakers else "UNAVAILABLE"

    return {
        "segments": normalized_segments,
        "speakers": speakers,
        "status": status,
    }
