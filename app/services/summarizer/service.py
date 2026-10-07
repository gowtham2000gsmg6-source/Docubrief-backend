import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.documents import SummaryStyle
from app.services.summarizer.chunking import chunk_text


class _SummaryPayload(BaseModel):
    title: str
    summary_text: str
    key_points: list[str]


@dataclass(frozen=True)
class SummaryResult:
    title: str
    summary_text: str
    key_points: list[str]
    model_used: str
    token_count: int | None


def _client() -> OpenAI:
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("LLM_API_KEY must be configured to generate summaries.")
    kwargs: dict[str, Any] = {"api_key": api_key}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return OpenAI(**kwargs)


def _request_summary(client: OpenAI, text: str, style: SummaryStyle, *, reducing: bool) -> tuple[_SummaryPayload, str, int | None]:
    settings = get_settings()
    task = "Combine the supplied partial summaries into one coherent final summary." if reducing else "Summarize this document excerpt faithfully."
    prompt = (
        f"{task} Requested style: {style.value}. "
        "Return a JSON object with exactly these fields: title (short document title), "
        "summary_text (the summary), key_points (array of concise takeaways). "
        "Do not invent facts. For Bullet points style, make summary_text a readable bullet list."
    )
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "You are a careful document summarizer. Return only valid JSON."},
            {"role": "user", "content": f"{prompt}\n\nCONTENT:\n{text}"},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The configured language model returned an empty summary.")
    try:
        payload = _SummaryPayload.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("The configured language model returned an invalid summary response.") from exc
    usage = response.usage.total_tokens if response.usage else None
    return payload, response.model or settings.llm_model, usage


def summarize_text(text: str, style: SummaryStyle) -> SummaryResult:
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("There is no extracted text to summarize.")
    settings = get_settings()
    client = _client()
    partials: list[str] = []
    model_names: list[str] = []
    token_count = 0
    has_usage = False

    def record_usage(model: str, tokens: int | None) -> None:
        nonlocal token_count, has_usage
        model_names.append(model)
        if tokens is not None:
            token_count += tokens
            has_usage = True

    for chunk in chunks:
        result, model, tokens = _request_summary(client, chunk, style, reducing=False)
        partials.append(
            json.dumps(
                {
                    "title": result.title,
                    "summary_text": result.summary_text,
                    "key_points": result.key_points,
                },
                ensure_ascii=False,
            )
        )
        record_usage(model, tokens)

    reduce_input = "\n\n".join(partials)
    while len(reduce_input) > settings.llm_chunk_chars:
        groups = chunk_text(
            reduce_input,
            max_chars=settings.llm_chunk_chars,
            overlap=0,
        )
        reduced: list[str] = []
        for group in groups:
            result, model, tokens = _request_summary(client, group, style, reducing=True)
            reduced.append(
                json.dumps(
                    {
                        "title": result.title,
                        "summary_text": result.summary_text,
                        "key_points": result.key_points,
                    },
                    ensure_ascii=False,
                )
            )
            record_usage(model, tokens)
        next_input = "\n\n".join(reduced)
        if len(next_input) >= len(reduce_input):
            raise ValueError("The document produced too many partial summaries to combine safely.")
        reduce_input = next_input

    final, final_model, tokens = _request_summary(client, reduce_input, style, reducing=True)
    record_usage(final_model, tokens)
    return SummaryResult(
        title=final.title,
        summary_text=final.summary_text,
        key_points=final.key_points,
        model_used=", ".join(sorted(set(model_names))),
        token_count=token_count if has_usage else None,
    )
