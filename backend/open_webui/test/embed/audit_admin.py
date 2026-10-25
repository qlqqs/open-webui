"""Offline AST inventory complementing grep (includes dict/getattr/admin dependencies).

Run: PYTHONPATH=backend python -m open_webui.test.embed.audit_admin
No imports of the application, database initialization or network access.
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def scan(root=ROOT):
    entries = []
    for path in sorted(root.rglob('*.py')):
        if any(part in ('test', 'migrations', '__pycache__') for part in path.relative_to(root).parts):
            continue
        source = path.read_text()
        tree = ast.parse(source)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            kind = None
            if isinstance(node, ast.Compare) and any(
                isinstance(child, ast.Constant) and child.value == 'admin' for child in ast.walk(node)
            ):
                kind = 'admin条件'
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == 'resource_admin':
                    kind = '收紧'
                if node.func.id == 'Depends' and any(
                    isinstance(arg, ast.Name) and arg.id == 'get_admin_user' for arg in node.args
                ):
                    kind = 'admin依赖'
            if not kind:
                continue
            names = []
            parent = node
            while parent in parents:
                parent = parents[parent]
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(parent.name)
            entries.append(
                {
                    'file': str(path.relative_to(root)),
                    'line': node.lineno,
                    'function': '.'.join(reversed(names)) or '<module>',
                    'kind': kind,
                    'expression': ast.unparse(node),
                    'source': source.splitlines()[node.lineno - 1].strip(),
                }
            )
    return entries


if __name__ == '__main__':
    print(json.dumps(scan(), ensure_ascii=False, indent=2))
