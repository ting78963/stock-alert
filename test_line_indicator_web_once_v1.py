import unittest
from unittest.mock import patch
import main

class TestWebOnce(unittest.TestCase):
    def test_send_once_without_state_mutation(self):
        main._line_indicator_test_sent=False
        fake=type("Response",(),{"status_code":200})()
        with patch.dict(main.os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"fake-token","LINE_TO_ID":"recognition-group","GROUP_ID":"wrong-old-group"}),patch.object(main.requests,"post",return_value=fake) as send:
            client=main.app.test_client()
            first=client.get("/audit/line-indicator-recognition-once-20261026-72d4af")
            second=client.get("/audit/line-indicator-recognition-once-20261026-72d4af")
            self.assertEqual(first.status_code,200)
            self.assertTrue(first.json["test_only"])
            self.assertTrue(second.json["already_sent"])
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.kwargs["json"]["to"],"recognition-group")
            payload=send.call_args.kwargs["json"]["messages"][0]
            self.assertIn("測試訊號",str(payload))
            self.assertIn("OSC",str(payload))
            self.assertIn("強勢買進",str(payload))
            self.assertEqual(len(send.call_args.kwargs["json"]["messages"]),1)

if __name__=="__main__":unittest.main()
