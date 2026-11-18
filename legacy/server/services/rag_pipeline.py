from typing import Generator
from openai import OpenAI
from config import OPENAI_API_KEY
from utils.prompts import build_prompt
from guardrails.hallucination import is_hallucinated
from services.confidence import get_confidence

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_answer(docs: list, query: str, retriever) -> dict:
    """
    Generate an answer from retrieved docs.
    If hallucination is detected, re-retrieves with more docs and retries once.
    """
    context = "\n\n".join([d.page_content for d in docs])
    prompt = build_prompt(context, query)

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        answer = res.choices[0].message.content
    except Exception:
        return {"answer": "Error generating answer", "sources": [], "confidence": 0}

    # Hallucination check — re-retrieve with more context if flagged
    if is_hallucinated(answer, context):
        docs = retriever(query, k=6)
        context = "\n\n".join([d.page_content for d in docs])
        prompt = build_prompt(context, query)
        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            answer = res.choices[0].message.content
        except Exception:
            pass  # keep original answer if retry fails

    confidence = get_confidence(answer, context)

    # Extract page references from chunk content
    sources = []
    for d in docs:
        if "[Page" in d.page_content:
            sources.append(d.page_content.split("]")[0] + "]")

    return {
        "answer": answer,
        "sources": list(set(sources)),
        "confidence": confidence
    }


def stream_answer(prompt: str) -> Generator[str, None, None]:
    """Stream an answer token by token for compare endpoint."""
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        yield f"\n[Stream error: {str(e)}]"
