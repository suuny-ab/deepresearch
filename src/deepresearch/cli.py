import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.runner import build_agent

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

    def _with_progress(label: str, node):
        def wrapped(state):
            console.print(label)
            return node(state)

        return wrapped

    return build_agent(
        llm=llm,
        search=search,
        max_subquestions=config.max_subquestions,
        results_per_query=config.results_per_query,
        output_dir=config.output_dir,
        wrap_node=_with_progress,
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
