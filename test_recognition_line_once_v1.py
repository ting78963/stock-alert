import unittest
from unittest.mock import patch,Mock
import main

class RecognitionOnlyTest(unittest.TestCase):
    def test_dedicated_destination(self):
        route="/audit/line-indicator-recognition-once-20261027-72d4af"
        with patch.dict(main.os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"recognition-token","LINE_TO_ID":"recognition-id","GROUP_ID":"legacy-id"}), patch.object(main.requests,"post",return_value=Mock(status_code=200)) as send:
            r=main.app.test_client().get(route)
            self.assertEqual(r.status_code,200,r.get_json())
            self.assertEqual(send.call_args.kwargs["json"]["to"],"recognition-id")
            self.assertIn("recognition-token",send.call_args.kwargs["headers"]["Authorization"])
            r=main.app.test_client().get(route)
            self.assertTrue(r.get_json().get("already_sent"))
            self.assertEqual(send.call_count,1)

if __name__=="__main__":unittest.main()
