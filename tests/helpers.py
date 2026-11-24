"""Authenticated client for existing business tests; uses the real account endpoints."""
from fastapi.testclient import TestClient

TEST_EMAIL = "regression@epita.fr"
TEST_USERNAME = "Compte de régression"
TEST_PASSWORD = "Mot de passe fictif pour les tests 2026!"


def enable_test_mailer(app):
    outbox = {}
    app.state.auth.email_sender = lambda email, token: outbox.__setitem__(email, token)
    app.state.test_email_outbox = outbox
    return outbox


def register_verified(client, email, username, password):
    outbox = getattr(client.app.state, "test_email_outbox", None) or enable_test_mailer(client.app)
    response = client.post("/api/auth/register", json={"email": email, "username": username, "password": password})
    assert response.status_code == 202, response.text
    token = outbox.get(email.strip().lower())
    if token:
        confirmed = client.post("/api/auth/verification/confirm", json={"token": token})
        assert confirmed.status_code == 200, confirmed.text
    else:
        confirmed = client.post("/api/auth/login", json={"identifier": email, "password": password})
        assert confirmed.status_code == 200, confirmed.text
    client.headers["X-CSRF-Token"] = confirmed.json()["csrfToken"]
    return confirmed


class AuthenticatedTestClient(TestClient):
    def __enter__(self):
        super().__enter__()
        try:
            enable_test_mailer(self.app)
            response = register_verified(self, TEST_EMAIL, TEST_USERNAME, TEST_PASSWORD)
            assert response.status_code == 200, response.text
            self.user = response.json()["user"]
            self.headers["X-CSRF-Token"] = response.json()["csrfToken"]
            return self
        except BaseException:
            super().__exit__(None, None, None)
            raise
