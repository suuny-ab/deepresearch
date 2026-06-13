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

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_app(config: AppConfig):
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
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int = typer.Option(5, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int = typer.Option(5, "--results-per-query", help="Tavily results per query"),
    output_dir: str = typer.Option("reports", "--output-dir", help="Report output directory"),
    model: str = typer.Option("deepseek-v4-pro", "--model", help="DeepSeek model"),
):
    try:
        config = AppConfig.from_env().with_overrides(
            max_subquestions=max_subquestions,
            results_per_query=results_per_query,
            output_dir=output_dir,
            model=model,
        )
        config.validate_required()

        console.print("[1/6] Planning research...")
        console.print("[2/6] Searching web...")
        console.print("[3/6] Preparing evidence...")
        console.print("[4/6] Writing report...")
        console.print("[5/6] Reviewing report...")
        console.print("[6/6] Saving report...")

        research_app = _build_app(config)
        result = research_app.invoke({"question": question, "errors": []})

        if result.get("report_status") == "failed_validation":
            console.print("\n[bold red]Report validation failed.[/bold red]")
            console.print(f"Saved failure report to: {result['output_path']}")
        else:
            console.print(f"\nSaved report to: {result['output_path']}")

        console.print(Markdown(result.get("report_markdown", "")))

    except ConfigError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except DeepResearchError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
