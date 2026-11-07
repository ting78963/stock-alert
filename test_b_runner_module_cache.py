import ast
import pathlib
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).with_name("production_worker_v2_shared_ws.py")


class RunnerModuleCacheTests(unittest.TestCase):
    def test_source_compiles(self):
        compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec")

    def test_load_once_for_many_stocks_and_threads(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        names = {"runner_module", "_runner_module_cache", "_runner_module_lock"}
        nodes = [n for n in tree.body if
                 isinstance(n, (ast.FunctionDef, ast.Assign)) and
                 (isinstance(n, ast.FunctionDef) and n.name == "runner_module"
                  or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
        calls = []
        sentinel = {"Runner": object()}
        def fake_run(path, run_name):
            calls.append((path, run_name))
            return sentinel
        namespace = {"threading": threading, "runpy": type("Runpy", (), {"run_path": staticmethod(fake_run)}),
                     "BR": "fake_runner.py", "str": str}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: namespace["runner_module"](), range(64)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(x is sentinel for x in results))


if __name__ == "__main__":
    unittest.main()
