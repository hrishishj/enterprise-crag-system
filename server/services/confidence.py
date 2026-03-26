import re
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def get_confidence(answer: str, context: str) -> float:
    """Return a 0–1 confidence score for how well the answer is supported by context."""
    prompt = f"""Rate how well the answer is supported by the context.
Respond with ONLY a number between 0 and 1 (e.g. 0.85).

Context:
{context}

Answer:
{answer}

Score:"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        text = res.choices[0].message.content.strip()
        match = re.search(r"\d*\.?\d+", text)
        score = float(match.group()) if match else 0.5
        return max(0.0, min(1.0, score))   # clamp to valid range
    except Exception:
        return 0.5
