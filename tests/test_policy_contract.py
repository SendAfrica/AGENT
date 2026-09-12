from __future__ import annotations

import unittest

from sendafrica_agent.policy import confirmation_decision, confirmation_payload, sms_parts


class PolicyContractTests(unittest.TestCase):
    def test_every_side_effect_requires_confirmation(self):
        cases = [
            ("send_sms", {"to": "+255700000001", "message": "Hello"}),
            ("send_bulk_sms", {"recipients": ["+255700000001"], "message": "Hello"}),
            ("create_campaign", {"name": "Launch"}),
            ("send_email", {"to": ["user@example.com"]}),
            ("request_sender_id", {"name": "SEND"}),
            ("import_contacts", {"list_id": "list-1", "csv_content": "phone\n+255700000001"}),
        ]
        for tool_name, args in cases:
            with self.subTest(tool_name=tool_name):
                self.assertTrue(confirmation_decision(tool_name, args).required)

    def test_read_only_tools_do_not_require_confirmation(self):
        for tool_name in ("get_account_balance", "list_contacts", "get_delivery_status", "list_contact_lists"):
            with self.subTest(tool_name=tool_name):
                self.assertFalse(confirmation_decision(tool_name, {}).required)

    def test_long_unicode_message_preview_reports_parts_and_credits(self):
        message = "🙂" * 71
        parts, encoding = sms_parts(message)
        preview = confirmation_payload("send_sms", {"to": "+255700000001", "message": message})
        self.assertEqual(encoding, "Unicode")
        self.assertEqual(parts, 2)
        self.assertEqual(preview["sms_parts"], 2)
        self.assertEqual(preview["estimated_credits"], 2)

    def test_bulk_preview_scales_estimate_by_recipient_count(self):
        preview = confirmation_payload("send_bulk_sms", {
            "recipients": ["+255700000001", "+255700000002"],
            "message": "Hello",
        })
        self.assertEqual(preview["recipients_count"], 2)
        self.assertEqual(preview["estimated_credits"], 2)


if __name__ == "__main__":
    unittest.main()
