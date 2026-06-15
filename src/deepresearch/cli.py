import typer
from rich.console import Console
from rich.markdown import Markdown

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.clients.tavily_pool import PooledTavilyClient, TavilyKeyPool
from deepresearch.config import AppConfig
from deepresearch.errors import ConfigError, DeepResearchError
from deepresearch.runner import build_agent
from deepresearch.state import TokenUsage

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_app(config: AppConfig, architecture: str = "pipeline"):
    if config.deepseek_api_key is None:
        raise ConfigError("DEEPSEEK_API_KEY is not set")
    if config.tavily_api_key is None:
        raise ConfigError("TAVILY_API_KEY is not set")

    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    if len(config.tavily_api_keys) > 1:
        pool = TavilyKeyPool(config.tavily_api_keys)
        search = PooledTavilyClient(pool)
        console.print(f"[dim]Tavily key pool: {len(config.tavily_api_keys)} keys, ~{pool.remaining_total} calls remaining[/dim]")
    else:
        search = TavilySearchClient(api_key=config.tavily_api_key)

    def _with_progress(label: str, node):
        def wrapped(state):
            console.print(label)
            return node(state)

        return wrapped

    arch = architecture if architecture in ("pipeline", "multi-agent", "react") else "pipeline"
    return build_agent(
        llm=llm,
        search=search,
        max_subquestions=config.max_subquestions,
        results_per_query=config.results_per_query,
        output_dir=config.output_dir,
        wrap_node=_with_progress,
        architecture=arch,  # type: ignore[arg-type]
    )


@app.command()
def main(
    question: str = typer.Argument(..., help="Research question"),
    max_subquestions: int = typer.Option(3, "--max-subquestions", help="Maximum generated subquestions"),
    results_per_query: int = typer.Option(5, "--results-per-query", help="Tavily results per query"),
    output_dir: str = typer.Option("reports", "--output-dir", help="Report output directory"),
    model: str = typer.Option("deepseek-v4-pro", "--model", help="DeepSeek model"),
    architecture: str = typer.Option("pipeline", "--architecture", help="Agent architecture: pipeline, multi-agent, or react"),
):
    try:
        config = AppConfig.from_env().with_overrides(
            max_subquestions=max_subquestions,
            results_per_query=results_per_query,
            output_dir=output_dir,
            model=model,
        )
        config.validate_required()

        research_app = _build_app(config, architecture=architecture)
        result = research_app.invoke({"question": question, "errors": []})

        if result.get("report_status") == "failed_validation":
            console.print("\n[bold red]Report validation failed.[/bold red]")
            console.print(f"Saved failure report to: {result['output_path']}")
        else:
            console.print(f"\nSaved report to: {result['output_path']}")

        # Cost summary
        token_usage: list[TokenUsage] = result.get("token_usage", [])
        if token_usage:
            total_prompt = sum(u.prompt_tokens for u in token_usage)
            total_completion = sum(u.completion_tokens for u in token_usage)
            total_cost = sum(u.estimated_cost for u in token_usage)
            total_tokens = total_prompt + total_completion
            # Per-node breakdown
            node_summary: dict[str, int] = {}
            for u in token_usage:
                node_summary[u.node] = node_summary.get(u.node, 0) + u.prompt_tokens + u.completion_tokens
            parts = " · ".join(f"{node}({tokens:,})" for node, tokens in node_summary.items())
            console.print(
                f"[dim]💰 {total_tokens:,} tokens · ~${total_cost:.4f} · {parts}[/dim]"
            )

        console.print(Markdown(result.get("report_markdown", "")))

    except ConfigError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except DeepResearchError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
