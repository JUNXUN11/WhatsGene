"""Single-user auth: seed, login/logout, route gating, ownership (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, config, db  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = config.DATABASE_PATH
        self._old_user = config.AUTH_USERNAME
        self._old_pw = config.AUTH_PASSWORD
        self._old_cookie = config.COOKIE_SAMESITE, config.COOKIE_SECURE
        self._old_mode = config.AUTH_MODE
        # A ./start backend/.env says single; these tests cover login.
        config.AUTH_MODE = "multi"
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        config.AUTH_USERNAME = "reviewer"
        config.AUTH_PASSWORD = "s3cret-review"
        # The test client speaks plain http: a split-hosting backend/.env
        # (SameSite=None forces Secure) would drop the session cookie.
        config.COOKIE_SAMESITE, config.COOKIE_SECURE = "lax", False
        db.init_db()

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._old_db
        config.AUTH_USERNAME = self._old_user
        config.AUTH_PASSWORD = self._old_pw
        config.COOKIE_SAMESITE, config.COOKIE_SECURE = self._old_cookie
        config.AUTH_MODE = self._old_mode
        self._tmp.cleanup()


class TestPasswords(Base):
    def test_roundtrip_and_wrong_password(self):
        stored = auth.hash_password("hunter2-hunter2")
        self.assertTrue(auth.verify_password("hunter2-hunter2", stored))
        self.assertFalse(auth.verify_password("wrong password", stored))
        self.assertFalse(auth.verify_password("hunter2-hunter2", "not-a-hash"))
        self.assertFalse(auth.verify_password("", stored))

    def test_salts_differ(self):
        self.assertNotEqual(auth.hash_password("same"), auth.hash_password("same"))


class TestCookiePolicy(Base):
    def _login_cookie(self, client) -> str:
        res = client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
        self.assertEqual(res.status_code, 200)
        return res.headers.get("set-cookie", "")

    def test_default_cookie_is_lax(self):
        from fastapi.testclient import TestClient

        from app.main import app

        old = config.COOKIE_SAMESITE
        config.COOKIE_SAMESITE = "lax"
        try:
            with TestClient(app) as client:
                cookie = self._login_cookie(client)
        finally:
            config.COOKIE_SAMESITE = old
        self.assertIn("samesite=lax", cookie.lower())
        self.assertIn("httponly", cookie.lower())

    def test_split_hosting_cookie_is_none_and_secure(self):
        from fastapi.testclient import TestClient

        from app.main import app

        old_samesite, old_secure = config.COOKIE_SAMESITE, config.COOKIE_SECURE
        config.COOKIE_SAMESITE = "none"
        config.COOKIE_SECURE = False  # login must force Secure with None
        try:
            with TestClient(app) as client:
                cookie = self._login_cookie(client)
        finally:
            config.COOKIE_SAMESITE, config.COOKIE_SECURE = old_samesite, old_secure
        self.assertIn("samesite=none", cookie.lower())
        self.assertIn("secure", cookie.lower())


class TestSeed(Base):
    def test_seed_creates_user_and_adopts_orphan_jobs(self):
        orphan = db.create_job(question="q", raw_input="NP_000509")
        self.assertIsNone(orphan.get("user_id"))
        user = auth.ensure_seeded_user()
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "reviewer")
        adopted = db.get_job(orphan["id"])
        assert adopted is not None
        self.assertEqual(adopted["user_id"], user["id"])
        self.assertIsNone(auth.ensure_seeded_user())  # second call is a no-op

    def test_no_seed_without_password(self):
        config.AUTH_PASSWORD = ""
        self.assertIsNone(auth.ensure_seeded_user())
        self.assertIsNone(db.get_user_by_username("reviewer"))


class TestLoginFlow(Base):
    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app)

    def test_login_me_logout(self):
        with self._client() as client:
            me = client.get("/auth/me")
            self.assertEqual(me.status_code, 200)
            self.assertFalse(me.json()["authenticated"])
            bad = client.post("/auth/login", json={"username": "reviewer", "password": "nope"})
            self.assertEqual(bad.status_code, 401)
            ok = client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["username"], "reviewer")
            me2 = client.get("/auth/me")
            self.assertTrue(me2.json()["authenticated"])
            self.assertEqual(me2.json()["username"], "reviewer")
            out = client.post("/auth/logout")
            self.assertEqual(out.status_code, 200)
            me3 = client.get("/auth/me")
            self.assertFalse(me3.json()["authenticated"])

    def test_jobs_gated_until_login(self):
        with self._client() as client:
            self.assertEqual(client.get("/jobs").status_code, 401)
            self.assertEqual(client.post("/jobs", json={"sequence": "NP_000509"}).status_code, 401)
            self.assertEqual(client.get("/jobs/WG-NOPE").status_code, 401)
            client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
            self.assertEqual(client.get("/jobs").status_code, 200)
            self.assertEqual(client.get("/jobs/WG-NOPE").status_code, 404)

    def test_jobs_are_owned_per_user(self):
        auth.ensure_seeded_user()
        owner = db.get_user_by_username("reviewer")
        assert owner is not None
        other = db.create_user("intruder", auth.hash_password("x" * 12))
        job = db.create_job(question="q", raw_input="NP_000509", user_id=owner["id"])
        token = auth.create_session_token()
        db.create_session(other["id"], token, auth.session_expiry_iso())
        with self._client() as client:
            client.cookies.set(auth.SESSION_COOKIE, token)
            self.assertEqual(client.get(f"/jobs/{job['id']}").status_code, 404)
            self.assertEqual(client.get("/jobs").json(), [])
            self.assertEqual(
                client.post(f"/jobs/{job['id']}/ask", json={"question": "q?"}).status_code, 404)


class TestSingleMode(Base):
    """AUTH_MODE=single: the owner's own browser skips login (decision 016)."""

    LOCAL = "http://127.0.0.1:8000"

    def setUp(self) -> None:
        super().setUp()
        config.AUTH_MODE = "single"

    def _client(self, base_url: str = LOCAL, client_host: str = "127.0.0.1"):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, base_url=base_url, client=(client_host, 50000))

    def test_owner_browser_is_signed_in(self):
        with self._client() as client:
            me = client.get("/auth/me").json()
            self.assertTrue(me["authenticated"])
            self.assertTrue(me["auto"])
            self.assertEqual(me["username"], "reviewer")
            self.assertEqual(client.get("/jobs").status_code, 200)
            self.assertEqual(client.post("/jobs", json={"sequence": "NP_000509"}).status_code, 201)

    def test_localhost_and_ipv6_hosts_count(self):
        with self._client(base_url="http://localhost:8000") as client:
            self.assertTrue(client.get("/auth/me").json()["authenticated"])
        with self._client(base_url="http://[::1]:8000", client_host="::1") as client:
            self.assertTrue(client.get("/auth/me").json()["authenticated"])

    def test_network_client_must_log_in(self):
        with self._client(client_host="192.168.1.20") as client:
            self.assertFalse(client.get("/auth/me").json()["authenticated"])
            self.assertEqual(client.get("/jobs").status_code, 401)
            client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
            me = client.get("/auth/me").json()
            self.assertTrue(me["authenticated"])
            self.assertFalse(me["auto"])

    def test_dns_rebinding_host_is_refused(self):
        with self._client(base_url="http://evil.example:8000") as client:
            self.assertEqual(client.get("/jobs").status_code, 401)

    def test_proxied_request_is_refused(self):
        # A tunnel or reverse proxy on this machine connects from loopback.
        for header in ("X-Forwarded-For", "Forwarded", "X-Real-IP", "CF-Connecting-IP"):
            with self._client() as client:
                res = client.get("/jobs", headers={header: "203.0.113.9"})
                self.assertEqual(res.status_code, 401, header)

    def test_cross_site_page_is_refused(self):
        with self._client() as client:
            self.assertEqual(client.post("/jobs", json={"sequence": "NP_000509"},
                                         headers={"Origin": "https://evil.example"}).status_code, 401)
            self.assertEqual(client.get("/jobs", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 401)
            self.assertEqual(client.get("/jobs", headers={"Origin": "null"}).status_code, 401)
            self.assertEqual(client.get("/jobs", headers={"Origin": "http://127.0.0.1:8000",
                                                         "Sec-Fetch-Site": "same-origin"}).status_code, 200)

    def test_malformed_host_is_refused_not_crashed(self):
        self.assertFalse(auth.is_owner_browser("127.0.0.1", {"host": "[::1"}))
        self.assertFalse(auth.is_owner_browser("127.0.0.1", {"host": "127.0.0.1", "origin": "http://[bad"}))

    def test_multi_mode_ignores_owner_browser(self):
        config.AUTH_MODE = "multi"
        with self._client() as client:
            self.assertFalse(client.get("/auth/me").json()["authenticated"])
            self.assertEqual(client.get("/jobs").status_code, 401)

    def test_second_account_turns_login_on(self):
        with self._client() as client:
            self.assertTrue(client.get("/auth/me").json()["auto"])
            res = client.post("/users", json={"username": "amina", "password": "amina-pass-1"})
            self.assertEqual(res.status_code, 201)
            # The owner got a session in that response, so stays signed in.
            me = client.get("/auth/me").json()
            self.assertTrue(me["authenticated"])
            self.assertFalse(me["auto"])
        with self._client() as fresh:
            self.assertFalse(fresh.get("/auth/me").json()["authenticated"])
            self.assertEqual(fresh.get("/jobs").status_code, 401)


class TestFirstRun(Base):
    """No account yet: the owner picks one on the first-run page (decision 017)."""

    def setUp(self) -> None:
        super().setUp()
        config.AUTH_PASSWORD = ""
        config.AUTH_MODE = "single"

    def _client(self, client_host: str = "127.0.0.1"):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, base_url="http://127.0.0.1:8000", client=(client_host, 50000))

    def test_no_password_means_first_run_page(self):
        with self._client() as client:
            self.assertEqual(db.user_count(), 0)
            me = client.get("/auth/me").json()
            self.assertFalse(me["authenticated"])
            self.assertTrue(me["needs_setup"])

    def test_owner_creates_account_and_adopts_jobs(self):
        orphan = db.create_job(question="q", raw_input="NP_000509")
        with self._client() as client:
            res = client.post("/auth/setup", json={"username": "junxun", "password": "long-enough"})
            self.assertEqual(res.status_code, 201)
            me = client.get("/auth/me").json()
            self.assertTrue(me["authenticated"])
            self.assertTrue(me["owner"])
            self.assertEqual(me["username"], "junxun")
            again = client.post("/auth/setup", json={"username": "other", "password": "long-enough"})
            self.assertEqual(again.status_code, 403)
        self.assertEqual(db.get_job(orphan["id"])["user_id"], db.first_user()["id"])

    def test_network_browser_cannot_claim_owner(self):
        with self._client(client_host="192.168.1.20") as client:
            self.assertFalse(client.get("/auth/me").json()["needs_setup"])
            res = client.post("/auth/setup", json={"username": "intruder", "password": "long-enough"})
            self.assertEqual(res.status_code, 403)
        self.assertEqual(db.user_count(), 0)

    def test_empty_password_or_bad_username_is_refused(self):
        with self._client() as client:
            empty = client.post("/auth/setup", json={"username": "junxun", "password": ""})
            self.assertEqual(empty.status_code, 400)
            bad = client.post("/auth/setup", json={"username": "no spaces", "password": "long-enough"})
            self.assertEqual(bad.status_code, 400)
        self.assertEqual(db.user_count(), 0)

    def test_short_password_is_allowed(self):
        with self._client() as client:
            res = client.post("/auth/setup", json={"username": "junxun", "password": "1"})
            self.assertEqual(res.status_code, 201)


class TestAccounts(Base):
    """The owner adds, resets, and removes accounts; nobody else can."""

    def setUp(self) -> None:
        super().setUp()
        self.owner = auth.ensure_seeded_user()

    def _login(self, username: str, password: str):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        res = client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return client

    def test_owner_manages_accounts(self):
        owner = self._login("reviewer", "s3cret-review")
        res = owner.post("/users", json={"username": "amina", "password": "amina-pass-1"})
        self.assertEqual(res.status_code, 201)
        dup = owner.post("/users", json={"username": "amina", "password": "amina-pass-1"})
        self.assertEqual(dup.status_code, 400)
        users = owner.get("/users").json()
        self.assertEqual([u["username"] for u in users], ["reviewer", "amina"])
        self.assertEqual([u["owner"] for u in users], [True, False])
        self.assertNotIn("password_hash", users[1])
        amina = self._login("amina", "amina-pass-1")
        self.assertFalse(amina.get("/auth/me").json()["owner"])

    def test_member_cannot_manage_accounts(self):
        member = auth.create_account("amina", "amina-pass-1")
        client = self._login("amina", "amina-pass-1")
        self.assertEqual(client.get("/users").status_code, 403)
        self.assertEqual(client.post("/users", json={"username": "x", "password": "long-enough"}).status_code, 403)
        self.assertEqual(client.delete(f"/users/{self.owner['id']}").status_code, 403)
        self.assertEqual(client.post(f"/users/{member['id']}/password",
                                     json={"password": "long-enough"}).status_code, 403)

    def test_reset_password_logs_member_out(self):
        member = auth.create_account("amina", "amina-pass-1")
        member_client = self._login("amina", "amina-pass-1")
        owner = self._login("reviewer", "s3cret-review")
        res = owner.post(f"/users/{member['id']}/password", json={"password": "fresh-pass-2"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(member_client.get("/auth/me").json()["authenticated"])
        self._login("amina", "fresh-pass-2")
        self.assertEqual(owner.post(f"/users/{self.owner['id']}/password",
                                    json={"password": "fresh-pass-2"}).status_code, 400)

    def test_remove_moves_workflows_to_owner(self):
        member = auth.create_account("amina", "amina-pass-1")
        job = db.create_job(question="q", raw_input="NP_000509", user_id=member["id"])
        owner = self._login("reviewer", "s3cret-review")
        res = owner.delete(f"/users/{member['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["moved_workflows"], 1)
        self.assertIsNone(db.get_user(member["id"]))
        self.assertEqual(db.get_job(job["id"])["user_id"], self.owner["id"])
        self.assertEqual(owner.delete(f"/users/{self.owner['id']}").status_code, 400)

    def test_change_own_password(self):
        client = self._login("reviewer", "s3cret-review")
        wrong = client.post("/auth/password", json={"current_password": "nope", "new_password": "brand-new-pw"})
        self.assertEqual(wrong.status_code, 400)
        ok = client.post("/auth/password", json={"current_password": "s3cret-review",
                                                 "new_password": "brand-new-pw"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(client.get("/auth/me").json()["authenticated"])  # new session cookie
        self._login("reviewer", "brand-new-pw")

    def test_auto_signed_owner_changes_password_without_current(self):
        from fastapi.testclient import TestClient

        from app.main import app

        config.AUTH_MODE = "single"
        with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
            res = client.post("/auth/password", json={"new_password": "brand-new-pw"})
            self.assertEqual(res.status_code, 200)
        self._login("reviewer", "brand-new-pw")



class TestSignup(Base):
    """Create an account from the login page (decision 017)."""

    def setUp(self) -> None:
        super().setUp()
        self._old_signup = config.ALLOW_SIGNUP
        config.ALLOW_SIGNUP = True

    def tearDown(self) -> None:
        config.ALLOW_SIGNUP = self._old_signup
        super().tearDown()

    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app)

    def test_signup_creates_member_and_signs_in(self):
        owner = auth.ensure_seeded_user()
        db.create_job(question="q", raw_input="NP_000509", user_id=owner["id"])
        with self._client() as client:
            self.assertTrue(client.get("/auth/me").json()["signup"])
            res = client.post("/auth/register", json={"username": "amina", "password": "pw"})
            self.assertEqual(res.status_code, 201)
            me = client.get("/auth/me").json()
            self.assertTrue(me["authenticated"])
            self.assertFalse(me["owner"])
            self.assertEqual(client.get("/jobs").json(), [])  # never sees the owner's work
            self.assertEqual(client.get("/users").status_code, 403)
            dup = client.post("/auth/register", json={"username": "amina", "password": "pw"})
            self.assertEqual(dup.status_code, 400)

    def test_signup_off(self):
        auth.ensure_seeded_user()
        config.ALLOW_SIGNUP = False
        with self._client() as client:
            self.assertFalse(client.get("/auth/me").json()["signup"])
            res = client.post("/auth/register", json={"username": "amina", "password": "pw"})
            self.assertEqual(res.status_code, 403)
        self.assertEqual(db.user_count(), 1)

    def test_signup_cannot_create_the_owner(self):
        config.AUTH_PASSWORD = ""
        with self._client() as client:
            self.assertFalse(client.get("/auth/me").json()["signup"])
            res = client.post("/auth/register", json={"username": "intruder", "password": "pw"})
            self.assertEqual(res.status_code, 403)
        self.assertEqual(db.user_count(), 0)


if __name__ == "__main__":
    unittest.main()
