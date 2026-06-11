import pytest

from deepresearch.config import AppConfig, ConfigError


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr("deepresearch.config.load_dotenv", lambda: None)


def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

    config = AppConfig.from_env()

    assert config.deepseek_api_key == "deepseek-key"
    assert config.tavily_api_key == "tavily-key"
    assert config.deepseek_model == "deepseek-v4-pro"
    assert config.max_subquestions == 5


def test_config_validates_required_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    config = AppConfig.from_env()

    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        config.validate_required()


def test_config_reports_invalid_max_subquestions(monkeypatch):
    monkeypatch.setenv("DEEPRESEARCH_MAX_SUBQUESTIONS", "abc")

    with pytest.raises(ConfigError, match="DEEPRESEARCH_MAX_SUBQUESTIONS"):
        AppConfig.from_env()


def test_config_reports_invalid_results_per_query(monkeypatch):
    monkeypatch.setenv("DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY", "abc")

    with pytest.raises(ConfigError, match="DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY"):
        AppConfig.from_env()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_config_rejects_non_positive_max_subquestions(monkeypatch, value):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("DEEPRESEARCH_MAX_SUBQUESTIONS", value)

    config = AppConfig.from_env()

    with pytest.raises(ConfigError, match="DEEPRESEARCH_MAX_SUBQUESTIONS"):
        config.validate_required()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_config_rejects_non_positive_results_per_query(monkeypatch, value):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY", value)

    config = AppConfig.from_env()

    with pytest.raises(ConfigError, match="DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY"):
        config.validate_required()


def test_config_with_overrides_preserves_zero_max_subquestions_for_validation():
    config = AppConfig(deepseek_api_key="deepseek-key", tavily_api_key="tavily-key")

    overridden = config.with_overrides(max_subquestions=0)

    assert overridden.max_subquestions == 0
    with pytest.raises(ConfigError, match="DEEPRESEARCH_MAX_SUBQUESTIONS"):
        overridden.validate_required()


def test_config_with_overrides_preserves_zero_results_per_query_for_validation():
    config = AppConfig(deepseek_api_key="deepseek-key", tavily_api_key="tavily-key")

    overridden = config.with_overrides(results_per_query=0)

    assert overridden.results_per_query == 0
    with pytest.raises(ConfigError, match="DEEPRESEARCH_SEARCH_RESULTS_PER_QUERY"):
        overridden.validate_required()
