import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.verbose import format_verbose_summary

app = typer.Typer(no_args_is_help=True)
console = Console()


def _with_progress(label: str, node):
    def wrapped(state):
        console.print(label)
        return node(state)

    return wrapped


def _build_app(config: AppConfig, dry_run: bool = False):
    assert config.deepseek_api_key is not None
    assert config.tavily_api_key is not None
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)

    plan_research = make_plan_research_node(llm, config.max_subquestions)
    search_web = make_search_web_node(search, config.results_per_query)
    prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
    synthesize_notes = make_synthesize_notes_node(llm)
    write_report = make_write_report_node(llm)
    review_report = make_review_report_node(llm)
    save_report = make_save_report_node(config.output_dir)

    return create_research_app(
        plan_research=_with_progress("[1/7] Planning research...", plan_research),
        search_web=_with_progress("[2/7] Searching web...", search_web),
        prepare_evidence=_with_progress("[3/7] Preparing evidence...", prepare_evidence),
        synthesize_notes=_with_progress("[4/7] Synthesizing notes...", synthesize_notes),
        write_report=_with_progress("[5/7] Writing report...", write_report),
        review_report=_with_progress("[6/7] Reviewing report...", review_report),
        save_report=_with_progress("[7/7] Saving report...", save_report),
        dry_run=dry_run,
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int | None = typer.Option(None, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int | None = typer.Option(None, "--results-per-query", help="Tavily results per query"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Report output directory"),
    model: str | None = typer.Option(None, "--model", help="DeepSeek model override"),
    verbose: bool = typer.Option(False, "--verbose", help="Print debugging details"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Stop after evidence extraction and print card summary"),
):
    try:
        config = AppConfig.from_env().with_overrides(
            max_subquestions=max_subquestions,
            results_per_query=results_per_query,
            output_dir=output_dir,
            model=model,
            verbose=verbose,
        )
        config.validate_required()
        research_app = _build_app(config, dry_run=dry_run)

        result = research_app.invoke({"question": question, "errors": []})

        if dry_run:
            console.print("\n[Dry run] Evidence extraction complete.\n")
            evidence_metrics = result.get("evidence_metrics", {})
            cards = result.get("evidence_cards", [])
            console.print(f"EvidenceCards: {evidence_metrics.get('evidence_cards', 0)}")
            console.print()
            console.print("Evidence corroboration:")
            corroboration = evidence_metrics.get("corroboration", {})
            for key in ["strongly_corroborated", "weakly_corroborated", "single_source"]:
                value = corroboration.get(key, 0)
                desc = {
                    "strongly_corroborated": " (3+ independent sources agree)",
                    "weakly_corroborated": " (2 independent sources agree)",
                    "single_source": " (only one source mentions this)",
                }.get(key, "")
                console.print(f"- {key}: {value}{desc}")
            if cards:
                console.print()
                console.print("Evidence card summaries:")
                for i, card in enumerate(cards, start=1):
                    claim_snippet = card.claim[:100] + "..." if len(card.claim) > 100 else card.claim
                    console.print(f"{i}. [{card.id}] {claim_snippet} (corroboration: {card.corroboration_level}, sources: {len(card.corroborating_sources)})")
            return

        if result.get("report_status") == "failed_validation":
            console.print("\nReport validation failed.")
            console.print(f"Saved failure report to: {result['output_path']}")
            console.print("Run again or use --verbose to inspect intermediate workflow details.\n")
        else:
            console.print(f"\nSaved report to: {result['output_path']}\n")
        console.print(Markdown(result.get("report_markdown", "")))

        if verbose:
            console.print("\n" + format_verbose_summary(result))
    except ConfigError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc
    except DeepResearchError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
