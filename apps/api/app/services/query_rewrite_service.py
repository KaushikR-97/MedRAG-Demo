from app.core.config import settings

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None
    ChatPromptTemplate = None


class QueryRewriteService:
    """Creates medical search rewrites before retrieval.

    If the rewrite model is unavailable, it returns the original query. This
    keeps retrieval robust during local demos and tests.
    """

    def rewrite(
        self,
        *,
        question: str,
        user_role: str,
        route: str,
        conversation_context: str = "",
    ) -> list[str]:
        if not question.strip():
            return []
        if not settings.openai_api_key or ChatOpenAI is None or ChatPromptTemplate is None:
            return [question]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Rewrite the user's medical query into up to 3 concise retrieval queries. "
                    "Include synonyms for Indian lab reports and clinical language when useful. "
                    "Do not answer the question. Return one query per line, no bullets.",
                ),
                (
                    "human",
                    "Role: {user_role}\nRoute: {route}\nPrior user context: "
                    "{conversation_context}\nCurrent question: {question}",
                ),
            ]
        )
        model = ChatOpenAI(
            model=settings.query_rewrite_model or settings.query_router_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        try:
            response = (prompt | model).invoke(
                {
                    "user_role": user_role,
                    "route": route,
                    "conversation_context": conversation_context or "None",
                    "question": question,
                }
            )
        except Exception:
            return [question]
        rewrites = [
            line.strip(" -\t")
            for line in str(response.content).splitlines()
            if line.strip(" -\t")
        ]
        unique = []
        for query in [question, *rewrites]:
            if query not in unique:
                unique.append(query)
        return unique[: settings.query_rewrite_max_queries]
