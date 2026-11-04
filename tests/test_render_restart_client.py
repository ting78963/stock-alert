import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("restart_client", Path(__file__).resolve().parents[1] / "tools" / "render_restart_client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

class RestartClientTests(unittest.TestCase):
    @patch("sys.argv", ["restart"])
    @patch.object(client.urllib.request, "urlopen")
    def test_default_dry_run(self, request):
        self.assertEqual(client.main(), 0)
        request.assert_not_called()

    @patch("sys.argv", ["restart", "--execute", "--approved"])
    @patch.dict(os.environ, {"ALLOW_WORKER_RESTART": "no", "RENDER_API_KEY": "secret"})
    @patch.object(client.urllib.request, "urlopen")
    def test_disabled(self, request):
        self.assertEqual(client.main(), 2)
        request.assert_not_called()

    @patch("sys.argv", ["restart", "--execute", "--approved"])
    @patch.dict(os.environ, {"ALLOW_WORKER_RESTART": "yes", "RENDER_API_KEY": "secret"})
    @patch.object(client.urllib.request, "urlopen")
    def test_accepted(self, request):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        request.return_value = response
        self.assertEqual(client.main(), 0)
        req = request.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertTrue(req.full_url.endswith("/restart"))

    @patch("sys.argv", ["restart", "--execute", "--approved"])
    @patch.dict(os.environ, {"ALLOW_WORKER_RESTART": "yes", "RENDER_API_KEY": "secret"})
    @patch.object(client.urllib.request, "urlopen")
    def test_non_success(self, request):
        response = MagicMock()
        response.__enter__.return_value.status = 500
        request.return_value = response
        self.assertEqual(client.main(), 1)

if __name__ == "__main__":
    unittest.main()
