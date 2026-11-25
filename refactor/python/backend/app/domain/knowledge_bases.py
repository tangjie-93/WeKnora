"""Safe failures and fixed bounds for the empty knowledge-base subset."""

BODY_LIMIT = 1024 * 1024
MAX_KNOWLEDGE_BASES = 100
KNOWLEDGE_BASE_PATH = "/api/v1/knowledge-bases"
SUPPORTED_STORAGE = ("local", "minio", "cos", "tos", "s3", "oss", "ks3", "obs")
# Go unicode.IsSpace, not Python's broader str.isspace (which includes U+001C..001F).
GO_WHITESPACE = "\t\n\v\f\r \u0085                 　"


class KnowledgeBaseFailure(Exception):
    """Carry only a fixed safe message across the HTTP boundary."""

    def __init__(self, status: int, code: int, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def invalid(message: str = "Invalid knowledge base request") -> KnowledgeBaseFailure:
    return KnowledgeBaseFailure(400, 1000, message)


def storage_failure() -> KnowledgeBaseFailure:
    return KnowledgeBaseFailure(500, 1007, "Knowledge base storage failure")


def unsupported_configuration() -> KnowledgeBaseFailure:
    return KnowledgeBaseFailure(503, 1008, "Knowledge base configuration is outside supported scope")
