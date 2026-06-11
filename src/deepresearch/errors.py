class DeepResearchError(Exception):
    pass


class ConfigError(DeepResearchError):
    pass


class LLMError(DeepResearchError):
    pass


class SearchError(DeepResearchError):
    pass


class ReportWriteError(DeepResearchError):
    pass
