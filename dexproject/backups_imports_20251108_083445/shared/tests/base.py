from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import Mock, patch

User = get_user_model()


class BaseDexTestCase(TestCase):
    """
    Base test case with common setup and utilities.
    """

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.user = self.create_test_user()

    def create_test_user(self, username='testuser', email='test@example.com'):
        """Create a test user."""
        return User.objects.create_user(
            username=username,
            email=email,
            password='testpass123'
        )

    def create_mock_web3(self):
        """Create a mock Web3 instance."""
        mock_w3 = Mock()
        mock_w3.eth.get_block_number.return_value = 18000000
        mock_w3.is_connected.return_value = True
        return mock_w3

    def assertEqualRounded(self, first, second, places=2):
        """Assert two decimal values are equal when rounded."""
        self.assertEqual(
            round(float(first), places),
            round(float(second), places)
        )
