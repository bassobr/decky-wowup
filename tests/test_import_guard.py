"""Decky Loader 3.2.9 dropped these stdlib modules from its PyInstaller bundle (decky-loader#968)."""
import ast
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
FORBIDDEN = {"glob", "configparser", "http.server", "socketserver", "difflib", "plistlib", "tomllib", "unittest",
             "webbrowser", "xml", "html"}


def _modules():
    base = os.path.join(ROOT, "py_modules", "wowaddons")
    files = [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".py")] + [os.path.join(ROOT, "main.py")]
    for path in files:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                yield path, node.module


def test_no_module_missing_from_decky_runtime():
    bad = [(os.path.basename(p), m) for p, m in _modules()
           if m in FORBIDDEN or any(m.startswith(f + ".") for f in FORBIDDEN)]
    assert not bad, f"imports unavailable inside Decky Loader: {bad}"
