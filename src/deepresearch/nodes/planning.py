from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.prompts.planning import build_planning_prompt
from deepresearch.state import ResearchState, SubQuestion
from deepresearch.utils.json import JSONParseError, parse_json_object


class PlanningResponse(BaseModel):
    subquestions: list[SubQuestion]


def make_plan_research_node(llm: LLMClient, max_subquestions: int):
    def plan_research(state: ResearchState) -> ResearchState:
        question = state["question"]
        errors = list(state.get("errors", []))
        prompt = build_planning_prompt(question, max_subquestions)
        text = llm.complete(prompt)
        try:
            parsed = parse_json_object(text, PlanningResponse)
            subquestions = parsed.subquestions[:max_subquestions]
        except JSONParseError as exc:
            errors.append(f"Planning JSON parse failed: {exc}")
            subquestions = [
                SubQuestion(
                    id="q1",
                    question=question,
                    search_query=question,
                    search_queries=[question],
                    rationale="Fallback from original question",
                )
            ]
        return {**state, "subquestions": subquestions, "errors": errors}

    return plan_research
