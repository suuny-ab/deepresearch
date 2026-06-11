import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.graph import create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.synthesizing import make_synthesize_notes_node
from deepresearch.nodes.writing import make_write_report_node

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_app(config: AppConfig):
    assert config.deepseek_api_key is not None
    assert config.tavily_api_key is not None
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)
    return create_research_app(
        plan_research=make_plan_research_node(llm, config.max_subquestions),
        search_web=make_search_web_node(search, config.results_per_query),
        synthesize_notes=make_synthesize_notes_node(llm),
        write_report=make_write_report_node(llm),
        review_report=make_review_report_node(llm),
        save_report=make_save_report_node(config.output_dir),
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int | None = typer.Option(None, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int | None = typer.Option(None, "--results-per-query", help="Tavily results per query"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Report output directory"),
    model: str | None = typer.Option(None, "--model", help="DeepSeek model override"),
    verbose: bool = typer.Option(False, "--verbose", help="Print debugging details"),
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
        research_app = _build_app(config)

        steps = [
            "[1/6] Planning research...",
            "[2/6] Searching web...",
            "[3/6] Synthesizing notes...",
            "[4/6] Writing report...",
            "[5/6] Reviewing report...",
            "[6/6] Saving report...",
        ]
        for step in steps:
            console.print(step)

        result = research_app.invoke({"question": question, "errors": []})
        console.print(f"\nSaved report to: {result['output_path']}\n")
        console.print(Markdown(result.get("report_markdown", "")))

        if verbose and result.get("errors"):
            console.print("\nErrors:")
            for error in result["errors"]:
                console.print(f"- {error}")
    except ConfigError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc
    except DeepResearchError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
