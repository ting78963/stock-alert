import unittest
from unittest.mock import patch
import main

class LegacyPushDisabled(unittest.TestCase):
    def test_legacy_sender_no_network(self):
        with patch.object(main.requests,"post") as post:
            self.assertFalse(main.send_line("legacy limit up"))
            post.assert_not_called()

    def test_legacy_manual_routes_disabled(self):
        client=main.app.test_client()
        for route in (
            "/audit/p1-flex-6207-9f2c7a",
            "/audit/flex-send-all-7c31",
            "/audit/indicator-help-flex-4d82",
            "/audit/line-indicator-once-20261026-5e91b7",
        ):
            with self.subTest(route=route):
                with patch.object(main.requests,"post") as post:
                    response=client.get(route)
                    self.assertEqual(response.status_code,410)
                    post.assert_not_called()

if __name__=="__main__": unittest.main()
