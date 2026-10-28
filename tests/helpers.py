"""Authenticated client for existing business tests; uses the real account endpoints."""
from fastapi.testclient import TestClient

TEST_EMAIL = "regression@epita.fr"
TEST_USERNAME = "Compte de régression"
TEST_PASSWORD = "Mot de passe fictif pour les tests 2026!"


class AuthenticatedTestClient(TestClient):
    def __enter__(self):
        super().__enter__()
        try:
            response = self.post("/api/auth/register", json={"email": TEST_EMAIL, "username": TEST_USERNAME, "password": TEST_PASSWORD})
            if response.status_code == 409:
                response = self.post("/api/auth/login", json={"identifier": TEST_EMAIL, "password": TEST_PASSWORD})
            assert response.status_code in {200, 201}, response.text
            self.user = response.json()["user"]
            self.headers["X-CSRF-Token"] = response.json()["csrfToken"]
            return self
        except BaseException:
            super().__exit__(None, None, None)
            raise
