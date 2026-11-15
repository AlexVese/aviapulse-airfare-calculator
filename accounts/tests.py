from django.contrib.auth import get_user_model
from django.test import TestCase

class AccountTests(TestCase):
    def test_registration_hash_login_logout_and_admin_permissions(self):
        password = "Route-7!example-private-pass"
        response = self.client.post("/accounts/register/", {"username": "analyst", "password1": password, "password2": password})
        self.assertRedirects(response, "/")
        user = get_user_model().objects.get(username="analyst")
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.is_staff)
        self.assertContains(self.client.get("/"), "analyst")
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.client.post("/accounts/logout/")
        self.assertNotIn("_auth_user_id", self.client.session)
        invalid = self.client.post("/accounts/login/", {"username": "analyst", "password": "incorrect"})
        self.assertEqual(invalid.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.post("/accounts/login/", {"username": "analyst", "password": password})
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
