from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def extract_clauses(context: str, clause_type: str) -> str:
    prompt = f"""Extract clauses related to: {clause_type}

Context:
{context}

Return bullet points."""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return res.choices[0].message.content
