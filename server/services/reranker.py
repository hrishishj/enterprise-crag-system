from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def rerank(query: str, docs: list, top_k: int = 3) -> list:
    """
    Re-rank retrieved documents by relevance to the query using LLM scoring.
    Falls back to returning top_k docs as-is if scoring fails.
    """
    if not docs:
        return []

    scored = []
    for doc in docs:
        try:
            prompt = f"""Rate how relevant this passage is to the query on a scale of 0.0 to 1.0.
Respond with ONLY a number (e.g. 0.85).

Query: {query}

Passage: {doc.page_content[:500]}

Score:"""
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10
            )
            text = res.choices[0].message.content.strip()
            score = float(text)
        except Exception:
            score = 0.5  # neutral fallback

        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]
