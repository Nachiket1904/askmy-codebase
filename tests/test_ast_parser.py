import tempfile
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ast_parser import parse_file, build_repo_map

PY_SOURCE = """\
import os
from pathlib import Path

class MyClass:
    def method_one(self):
        pass

def standalone_func(x, y):
    return x + y
"""

JS_SOURCE = """\
import fs from 'fs';

class JsClass {
    greet() {}
}

function jsFunc(a) {
    return a;
}
"""


def test_parse_python_file():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(PY_SOURCE)
        tmp = f.name
    try:
        result = parse_file(tmp)
        func_names = [fn["name"] for fn in result["functions"]]
        class_names = [c["name"] for c in result["classes"]]
        import_statements = [i["statement"] for i in result["imports"]]

        assert "standalone_func" in func_names, f"Expected standalone_func in {func_names}"
        assert "method_one" in func_names, f"Expected method_one in {func_names}"
        assert "MyClass" in class_names, f"Expected MyClass in {class_names}"
        assert any("os" in s for s in import_statements), f"Expected os import in {import_statements}"
        assert all("start_line" in fn for fn in result["functions"])
    finally:
        os.unlink(tmp)


def test_build_repo_map():
    with tempfile.TemporaryDirectory() as tmpdir:
        py_path = os.path.join(tmpdir, "sample.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(PY_SOURCE)

        repo_map = build_repo_map(tmpdir)

        assert len(repo_map) == 1
        key = list(repo_map.keys())[0]
        assert key.endswith("sample.py")
        entry = repo_map[key]
        assert "functions" in entry
        assert "classes" in entry
        assert "imports" in entry
        func_names = [fn["name"] for fn in entry["functions"]]
        assert "standalone_func" in func_names


if __name__ == "__main__":
    test_parse_python_file()
    print("test_parse_python_file passed")
    test_build_repo_map()
    print("test_build_repo_map passed")
