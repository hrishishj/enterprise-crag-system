from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def is_relevant(query: str) -> bool:
    """Returns True if the query is finance or legal related."""
    prompt = f"Is this a finance or legal query? Reply with only YES or NO.\n\nQuery: {query}"

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5
        )
        return "YES" in res.choices[0].message.content.strip().upper()
    except Exception:
        return True  # default: allow query through on error
