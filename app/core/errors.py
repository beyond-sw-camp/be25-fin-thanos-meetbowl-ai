class AiError(Exception):
    def __init__(
        self, code: str, message: str, *, retryable: bool = False, status_code: int = 500
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class ContextNotFoundError(AiError):
    def __init__(self, message: str = "회의록 생성 컨텍스트를 찾을 수 없습니다.") -> None:
        super().__init__("AI_CONTEXT_NOT_FOUND", message, retryable=True, status_code=404)


class ResponseValidationError(AiError):
    def __init__(self, message: str = "AI 응답 스키마 검증에 실패했습니다.") -> None:
        super().__init__("AI_RESPONSE_VALIDATION_FAILED", message, status_code=502)


class ProviderUnavailableError(AiError):
    def __init__(self, message: str = "LLM Provider를 사용할 수 없습니다.") -> None:
        super().__init__("AI_PROVIDER_UNAVAILABLE", message, retryable=True, status_code=503)


class ModelProfileNotConfiguredError(AiError):
    def __init__(self, model_profile: str) -> None:
        super().__init__(
            "AI_MODEL_PROFILE_NOT_CONFIGURED",
            f"AI 모델 프로필이 설정되지 않았습니다: {model_profile}",
            status_code=500,
        )


class ResponseParseError(AiError):
    def __init__(self, message: str = "LLM 응답 파싱에 실패했습니다.") -> None:
        super().__init__("AI_RESPONSE_PARSE_FAILED", message, status_code=502)


class DocumentIndexFailedError(AiError):
    def __init__(
        self,
        message: str = "문서 임베딩 또는 색인 처리에 실패했습니다.",
        *,
        retryable: bool = True,
    ) -> None:
        super().__init__(
            "AI_DOCUMENT_INDEX_FAILED",
            message,
            retryable=retryable,
            status_code=503 if retryable else 500,
        )
