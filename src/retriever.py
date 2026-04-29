import os

from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough


class _LLMChain:
    def __init__(self, prompt):
        self.prompt = prompt


class _CombineDocsChain:
    def __init__(self, prompt):
        self.llm_chain = _LLMChain(prompt)


class CodeRetrievalChain:
    return_source_documents = True

    def __init__(self, retriever, qa_prompt, llm):
        self.combine_docs_chain = _CombineDocsChain(qa_prompt)
        self._retriever = retriever
        self._llm = llm
        self._prompt = qa_prompt

    def __call__(self, inputs: dict) -> dict:
        question = inputs["question"]
        docs = self._retriever.invoke(question)
        context = "\n\n".join(d.page_content for d in docs)
        messages = self._prompt.format_messages(context=context, question=question)
        response = self._llm.invoke(messages)
        return {"answer": response.content, "source_documents": docs}


def _format_repo_map(repo_map: dict) -> str:
    lines = []
    for filepath, info in repo_map.items():
        fns = [f["name"] for f in info.get("functions", [])]
        cls = [c["name"] for c in info.get("classes", [])]
        parts = []
        if cls:
            parts.append(f"classes: {', '.join(cls)}")
        if fns:
            parts.append(f"functions: {', '.join(fns)}")
        summary = filepath + (f" [{'; '.join(parts)}]" if parts else "")
        lines.append(summary)
    return "\n".join(lines)


def load_index(index_path: str):
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    index = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    return index.as_retriever()


def build_chain(retriever, repo_map: dict) -> CodeRetrievalChain:
    repo_map_text = _format_repo_map(repo_map)

    system_template = (
        "You are an expert code assistant with deep knowledge of this repository.\n\n"
        "REPOSITORY STRUCTURE:\n"
        f"{repo_map_text}\n\n"
        "Use the repository map to understand file relationships and the retrieved "
        "code chunks to answer accurately. Always cite the source file."
    )

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_template),
        ("human", "RETRIEVED CODE:\n{context}\n\nQUESTION: {question}"),
    ])

    llm = ChatOpenAI(model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1-nano-2025-04-14"), temperature=0)

    return CodeRetrievalChain(retriever, qa_prompt, llm)
