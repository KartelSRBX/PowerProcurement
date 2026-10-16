from app.ai.base import AIResult, T
from app.ai.prompts import PromptTemplate


class AnthropicAdapter:
    """Live Claude API behind the common interface. The model name comes from config."""

    def __init__(self, api_key: str, model: str, max_tokens: int, client=None):
        if client is None:
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is empty; set it in .env or use AI_PROVIDER=mock")
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def extract(self, prompt: PromptTemplate, variables: dict[str, str], schema: type[T]) -> AIResult[T]:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt.render(variables)}],
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError(f"model returned no parsable answer (stop_reason={response.stop_reason})")
        return AIResult(
            parsed=parsed,
            model=self.model,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
