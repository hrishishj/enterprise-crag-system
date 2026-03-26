def build_prompt(context: str, query: str) -> str:
    return f"""Use the following context to answer the question accurately.
If the answer is not found in the context, say "I don't have enough information to answer this."

Context:
{context}

Question: {query}

Answer:"""


def build_comparison_prompt(grouped_docs: dict, query: str) -> str:
    comparison = ""
    for doc_name, contents in grouped_docs.items():
        comparison += f"\n\n=== {doc_name} ===\n"
        comparison += "\n".join(contents)

    return f"""Compare the following documents regarding: {query}

{comparison}

Provide a detailed comparison:"""
