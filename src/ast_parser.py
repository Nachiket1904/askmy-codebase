import os
from pathlib import Path

try:
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    from tree_sitter import Language, Parser
    PY_LANGUAGE = Language(tspython.language())
    JS_LANGUAGE = Language(tsjavascript.language())
    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False


def _parse_with_tree_sitter(source: str, language) -> dict:
    parser = Parser(language)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    functions = []
    classes = []
    imports = []

    def walk(node):
        if node.type in ("function_definition", "function_declaration", "method_definition"):
            for child in node.children:
                if child.type == "identifier":
                    functions.append({
                        "name": child.text.decode("utf-8"),
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                    })
                    break
        elif node.type == "class_definition":
            for child in node.children:
                if child.type == "identifier":
                    classes.append({
                        "name": child.text.decode("utf-8"),
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                    })
                    break
        elif node.type in ("import_statement", "import_from_statement",
                           "import_declaration", "export_statement"):
            imports.append({
                "statement": node.text.decode("utf-8").split("\n")[0].strip(),
                "line": node.start_point[0] + 1,
            })
        for child in node.children:
            walk(child)

    walk(root)
    return {"functions": functions, "classes": classes, "imports": imports}


def _parse_python_fallback(source: str) -> dict:
    import ast as pyast
    functions, classes, imports = [], [], []
    try:
        tree = pyast.parse(source)
    except SyntaxError:
        return {"functions": [], "classes": [], "imports": []}

    for node in pyast.walk(tree):
        if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            })
        elif isinstance(node, pyast.ClassDef):
            classes.append({
                "name": node.name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            })
        elif isinstance(node, pyast.Import):
            for alias in node.names:
                imports.append({"statement": f"import {alias.name}", "line": node.lineno})
        elif isinstance(node, pyast.ImportFrom):
            module = node.module or ""
            names = ", ".join(a.name for a in node.names)
            imports.append({"statement": f"from {module} import {names}", "line": node.lineno})

    return {"functions": functions, "classes": classes, "imports": imports}


def parse_file(filepath: str) -> dict:
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix not in (".py", ".js"):
        return {"functions": [], "classes": [], "imports": [], "error": "unsupported file type"}

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"functions": [], "classes": [], "imports": [], "error": str(e)}

    if TREE_SITTER_AVAILABLE:
        lang = PY_LANGUAGE if suffix == ".py" else JS_LANGUAGE
        result = _parse_with_tree_sitter(source, lang)
    elif suffix == ".py":
        result = _parse_python_fallback(source)
    else:
        result = {"functions": [], "classes": [], "imports": [], "error": "tree-sitter unavailable for .js"}

    result["filepath"] = str(path)
    return result


def build_repo_map(repo_path: str) -> dict:
    repo = Path(repo_path)
    repo_map = {}

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() in (".py", ".js"):
                rel = str(fpath.relative_to(repo))
                repo_map[rel] = parse_file(str(fpath))

    return repo_map
