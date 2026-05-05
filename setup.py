from setuptools import setup, find_packages

setup(
    name="askmy-codebase",
    version="0.1.0",
    description="Chat with any codebase using AI — local or GitHub repos",
    python_requires=">=3.9",
    packages=find_packages(include=["src", "src.*"]),
    install_requires=[
        "langchain>=0.3.0,<0.4.0",
        "langchain-core>=0.3.0,<0.4.0",
        "langchain-community>=0.3.0,<0.4.0",
        "langchain-openai>=0.3.0,<0.4.0",
        "langchain-text-splitters>=0.3.0,<0.4.0",
        "langchain-huggingface>=0.1.0,<0.2.0",
        "openai>=1.0.0,<2.0.0",
        "sentence-transformers>=3.0.0,<4.0.0",
        "faiss-cpu>=1.7.4,<2.0.0",
        "tree-sitter>=0.25.0,<0.26.0",
        "tree-sitter-python>=0.25.0,<0.26.0",
        "tree-sitter-javascript>=0.25.0,<0.26.0",
        "python-dotenv>=1.0.0,<2.0.0",
        "gitpython>=3.1.0",
    ],
    entry_points={
        "console_scripts": [
            "askmy-codebase=src.main:main",
        ],
    },
)
