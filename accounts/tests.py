from django.contrib.auth import get_user_model
from django.test import TestCase


class UserManagerTests(TestCase):
    def test_create_superuser_accepts_name_field(self):
        User = get_user_model()

        user = User.objects.create_superuser(
            email="admin@example.com",
            password="secret123",
            name="Admin User",
        )

        self.assertEqual(user.email, "admin@example.com")
        self.assertEqual(user.name, "Admin User")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
