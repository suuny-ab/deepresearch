from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.synthesizing import build_synthesizing_prompt
from deepresearch.state import ResearchNote, ResearchState
from deepresearch.utils.json import JSONParseError, parse_json_object


class NotesResponse(BaseModel):
    notes: list[ResearchNote]


def _fallback_notes(state: ResearchState) -> list[ResearchNote]:
    notes: list[ResearchNote] = []
    evidence_cards = state.get("evidence_cards", [])
    for subquestion in state.get("subquestions", []):
        matching = [card for card in evidence_cards if card.subquestion_id == subquestion.id]
        findings = [card.claim for card in matching[:3]] or ["No EvidenceCards were available for this subquestion; findings are low confidence."]
        urls = list(dict.fromkeys(card.source_url for card in matching))
        notes.append(ResearchNote(subquestion_id=subquestion.id, key_findings=findings, source_urls=urls, confidence="low"))
    return notes


def _invalid_source_constraint_errors(state: ResearchState, notes: list[ResearchNote]) -> list[str]:
    allowed_subquestion_ids = {subquestion.id for subquestion in state.get("subquestions", [])}
    allowed_urls = {card.source_url for card in state.get("evidence_cards", [])}
    unknown_subquestion_ids = sorted({note.subquestion_id for note in notes if note.subquestion_id not in allowed_subquestion_ids})
    unknown_urls = sorted({url for note in notes for url in note.source_urls if url not in allowed_urls})

    errors = []
    if unknown_subquestion_ids:
        errors.append(f"unknown subquestion_id values: {', '.join(unknown_subquestion_ids)}")
    if unknown_urls:
        errors.append(f"source_urls outside EvidenceCards: {', '.join(unknown_urls)}")
    return errors


def make_synthesize_notes_node(llm: LLMClient):
    def synthesize_notes(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        evidence_cards = state.get("evidence_cards", [])
        if not evidence_cards:
            errors.append("No EvidenceCards available for note synthesis; returning low-confidence fallback notes.")
            return {**state, "notes": _fallback_notes(state), "errors": errors}

        prompt = build_synthesizing_prompt(state["question"], state.get("subquestions", []), evidence_cards)
        text = llm.complete(prompt)
        try:
            notes = parse_json_object(text, NotesResponse).notes
            source_constraint_errors = _invalid_source_constraint_errors(state, notes)
            if source_constraint_errors:
                errors.append(f"Notes invalid source constraints: {'; '.join(source_constraint_errors)}")
                notes = _fallback_notes(state)
        except JSONParseError as exc:
            errors.append(f"Notes JSON parse failed: {exc}")
            notes = _fallback_notes(state)
        return {**state, "notes": notes, "errors": errors}

    return synthesize_notes
