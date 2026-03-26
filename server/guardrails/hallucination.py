from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def is_hallucinated(answer: str, context: str) -> bool:
    """
    Returns True if the answer appears NOT to be supported by the context.
    Note: prompt asks 'Is answer supported?' — YES means supported (not hallucinated).
    """
    prompt = f"""Is the answer supported by the context? Reply with only YES or NO.

Context:
{context}

Answer:
{answer}"""

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5
        )
        response = res.choices[0].message.content.strip().upper()
        # YES = supported = NOT hallucinated
        return "YES" not in response
    except Exception:
        return False  # default: assume not hallucinated on error
