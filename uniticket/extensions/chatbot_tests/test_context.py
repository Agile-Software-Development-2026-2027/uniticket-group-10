from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from extensions.assistant.context import _get_identifier, get_user_context


class UserContextTest(SimpleTestCase):

    @patch("extensions.assistant.context.EMPLOYEE_ATTRIBUTE_NAME", "employee_id")
    def test_employee_identifier(self):
        user = Mock()
        user.employee_id = "12345"

        identifier, is_employee = _get_identifier(user)

        self.assertEqual(identifier, 12345)
        self.assertTrue(is_employee)

    @patch("extensions.assistant.context.USER_ATTRIBUTE_NAME", "user_id")
    @patch("extensions.assistant.context.EMPLOYEE_ATTRIBUTE_NAME", "employee_id")
    def test_regular_user_identifier(self):
        user = Mock()
        user.employee_id = None
        user.user_id = "67890"

        identifier, is_employee = _get_identifier(user)

        self.assertEqual(identifier, 67890)
        self.assertFalse(is_employee)

    @patch("extensions.assistant.context.USER_ATTRIBUTE_NAME", "user_id")
    @patch("extensions.assistant.context.EMPLOYEE_ATTRIBUTE_NAME", "employee_id")
    def test_missing_identifier(self):
        user = Mock()
        user.employee_id = None
        user.user_id = None

        with self.assertRaises(Exception):
            _get_identifier(user)

    def test_get_user_context_without_authenticated_user(self):
        request = Mock()
        request.user = None

        result = get_user_context(request)

        self.assertEqual(result, {})