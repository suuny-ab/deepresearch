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
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.verbose import format_verbose_summary

app = typer.Typer(no_args_is_help=True)
console = Console()


def _with_progress(label: str, node):
    def wrapped(state):
        console.print(label)
        return node(state)

    return wrapped


def _build_app(config: AppConfig, dry_run: bool = False, replay_search: bool = False):
    if config.deepseek_api_key is None:
        raise ConfigError("DEEPSEEK_API_KEY is not set")
    if config.tavily_api_key is None:
        raise ConfigError("TAVILY_API_KEY is not set")
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)

    plan_research = make_plan_research_node(llm, config.max_subquestions)
    search_web = make_search_web_node(search, config.results_per_query)
    prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)
    write_report = make_write_report_node(llm)
    review_report = make_review_report_node(llm)
    save_report = make_save_report_node(config.output_dir)

    return create_research_app(
        plan_research=_with_progress("[1/6] Planning research...", plan_research),
        search_web=_with_progress("[2/6] Searching web...", search_web),
        prepare_evidence=_with_progress("[3/6] Preparing evidence...", prepare_evidence),
        write_report=_with_progress("[4/6] Writing report...", write_report),
        review_report=_with_progress("[5/6] Reviewing report...", review_report),
        save_report=_with_progress("[6/6] Saving report...", save_report),
        dry_run=dry_run,
        replay_search=replay_search,
    )


def _run_compare(baseline_path: str, new_path: str):
    import json as json_module
    with open(baseline_path) as f:
        baseline = json_module.load(f)
    with open(new_path) as f:
        new = json_module.load(f)

    b_cards = baseline.get("evidence_cards", [])
    n_cards = new.get("evidence_cards", [])
    b_metrics = baseline.get("evidence_metrics", {})
    n_metrics = new.get("evidence_metrics", {})
    b_extracted = b_metrics.get("extracted_sources", 1) or 1
    n_extracted = n_metrics.get("extracted_sources", 1) or 1

    console.print("\nA/B Comparison: baseline vs new\n")
    console.print("Claim extraction:")
    console.print(f"  baseline: {len(b_cards)} cards from {b_extracted} sources ({len(b_cards)/max(b_extracted,1):.1f} avg)")
    console.print(f"  new:      {len(n_cards)} cards from {n_extracted} sources ({len(n_cards)/max(n_extracted,1):.1f} avg)")
    if len(b_cards) > 0:
        console.print(f"  delta: {((len(n_cards)-len(b_cards))/len(b_cards)*100):+.0f}%")

    b_corr = b_metrics.get("corroboration", {})
    n_corr = n_metrics.get("corroboration", {})
    console.print("\nCorroboration distribution:")
    console.print(f"  baseline: {b_corr}")
    console.print(f"  new:      {n_corr}")

    b_single = b_corr.get("single_source", 0)
    n_single = n_corr.get("single_source", 0)
    b_total = len(b_cards)
    n_total = len(n_cards)
    if b_total > 0 and n_total > 0:
        console.print(f"\nSingle-source rate: {b_single/b_total:.0%} -> {n_single/n_total:.0%}")


@app.command()
def main(
    question: str | None = typer.Argument(None, help="Research question"),
    max_subquestions: int | None = typer.Option(None, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int | None = typer.Option(None, "--results-per-query", help="Tavily results per query"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Report output directory"),
    model: str | None = typer.Option(None, "--model", help="DeepSeek model override"),
    verbose: bool = typer.Option(False, "--verbose", help="Print debugging details"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Stop after evidence extraction and print card summary"),
    save_search: str | None = typer.Option(None, "--save-search", help="Save search results for replay"),
    replay_search: str | None = typer.Option(None, "--replay-search", help="Replay from saved search results"),
    compare: tuple[str, str] | None = typer.Option(None, "--compare", help="Compare two dry-run JSON outputs"),
    output: str | None = typer.Option(None, "--output", help="Save dry-run output as JSON"),
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

        if not compare and not replay_search and not question:
            console.print("Error: question argument is required unless --compare or --replay-search is used")
            raise typer.Exit(code=1)

        # --compare mode
        if compare:
            _run_compare(compare[0], compare[1])
            return

        # --replay-search mode
        if replay_search:
            import json as json_module
            try:
                with open(replay_search) as f:
                    saved = json_module.load(f)
            except (FileNotFoundError, json_module.JSONDecodeError, KeyError) as exc:
                console.print(f"Error loading replay search file: {exc}")
                raise typer.Exit(code=1)
            research_app = _build_app(config, dry_run=True, replay_search=True)
            result = research_app.invoke({
                "question": saved["question"],
                "subquestions": saved["subquestions"],
                "search_results": saved["search_results"],
                "errors": [],
            })
        else:
            research_app = _build_app(config, dry_run=dry_run)
            result = research_app.invoke({"question": question, "errors": []})

        # --save-search
        if save_search:
            import json as json_module
            with open(save_search, "w") as f:
                json_module.dump({
                    "question": result.get("question", question),
                    "subquestions": result.get("subquestions", []),
                    "search_results": result.get("search_results", []),
                }, f, default=str, indent=2)
            console.print(f"Search results saved to {save_search}")

        # --output (dry-run or replay output)
        if output and (dry_run or replay_search):
            import json as json_module
            output_data = {
                "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
                "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
                "evidence_metrics": result.get("evidence_metrics", {}),
            }
            review = result.get("review")
            if review is not None:
                output_data["review"] = review.model_dump()
            output_data["review_rewritten"] = result.get("review_rewritten", False)
            output_data["report_status"] = result.get("report_status")
            with open(output, "w", encoding="utf-8") as f:
                json_module.dump(output_data, f, indent=2, default=str)
            console.print(f"Benchmark output saved to {output}")

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
            console.print()
            confidence = evidence_metrics.get("confidence", {})
            if confidence:
                console.print("Evidence confidence:")
                for key in ["high", "medium", "low"]:
                    if key in confidence:
                        console.print(f"- {key}: {confidence[key]}")
            if verbose:
                console.print("\n" + format_verbose_summary(result))
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
