import re
from typing import Any, Dict, List, Optional

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text.strip()) if s.strip()]


def structure_transcription(
    text: str,
    segments: Optional[List[Dict[str, Any]]] = None,
    max_paragraph_chars: int = 600,
) -> Dict[str, Any]:
    """Organise la transcription en paragraphes structurés et calcule les métriques statistiques."""
    normalized = text.strip()
    if not normalized:
        return {
            "paragraphs": [],
            "paragraph_count": 0,
            "sentence_count": 0,
            "word_count": 0,
            "character_count": 0,
        }

    valid_segments = [
        seg for seg in (segments or [])
        if isinstance(seg, dict) and seg.get("text")
    ]

    paragraphs: List[Dict[str, Any]] = []

    if valid_segments:
        current_parts: List[str] = []
        current_segments: List[Dict[str, Any]] = []
        current_len = 0

        def flush():
            if not current_parts:
                return
            p_text = " ".join(current_parts).strip()
            p_obj: Dict[str, Any] = {
                "index": len(paragraphs),
                "text": p_text,
                "sentences": _split_sentences(p_text),
            }
            if current_segments:
                starts = [s["start"] for s in current_segments if isinstance(s.get("start"), (int, float))]
                ends = [s["end"] for s in current_segments if isinstance(s.get("end"), (int, float))]
                speakers = list(dict.fromkeys(s["speaker"] for s in current_segments if s.get("speaker")))
                if starts:
                    p_obj["start"] = min(starts)
                if ends:
                    p_obj["end"] = max(ends)
                if speakers:
                    p_obj["speakers"] = speakers

            paragraphs.append(p_obj)
            current_parts.clear()
            current_segments.clear()

        for seg in valid_segments:
            seg_text = seg["text"].strip()
            if not seg_text:
                continue
            extra = len(seg_text) + (1 if current_parts else 0)
            if current_parts and (current_len + extra > max_paragraph_chars):
                flush()
                current_len = 0
            current_parts.append(seg_text)
            current_segments.append(seg)
            current_len += len(seg_text) + 1

        flush()

    # Fallback si aucun segment horodaté n'était disponible
    if not paragraphs and normalized:
        parts: List[str] = []
        curr = ""
        for s in _split_sentences(normalized):
            candidate = f"{curr} {s}".strip() if curr else s
            if curr and len(candidate) > max_paragraph_chars:
                parts.append(curr)
                curr = s
            else:
                curr = candidate
        if curr:
            parts.append(curr)

        paragraphs = [
            {"index": idx, "text": part, "sentences": _split_sentences(part)}
            for idx, part in enumerate(parts)
        ]

    total_sentences = sum(len(p.get("sentences", [])) for p in paragraphs)
    total_words = len(normalized.split())

    return {
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "sentence_count": total_sentences,
        "word_count": total_words,
        "character_count": len(normalized),
    }
