"""Phase 0 smoke test -- exercises the gateway in-process via ASGI transport.

No server, no ports: httpx talks straight to the FastAPI app, so this runs
identically on a laptop and in CI.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.main import app  # noqa: E402
from seed.seed import DEMO_PASSWORD  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((PASS if ok else FAIL, name, detail))
    return ok


async def main() -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30
    ) as c:
        # ---------------------------------------------------------- system --
        r = await c.get("/")
        check("GET /", r.status_code == 200 and r.json()["name"] == "MetriX",
              f"{r.status_code}")

        r = await c.get("/health")
        h = r.json()
        check("GET /health", r.status_code == 200 and h["status"] == "ok",
              f"db={h.get('database')} tasks={h.get('task_backend')} "
              f"store={h.get('storage_backend')} vision={h.get('vision_provider')}")

        r = await c.get("/health/capabilities")
        caps = r.json()
        check("GET /health/capabilities", r.status_code == 200,
              f"opencv={caps['computer_vision']['opencv']} "
              f"shapely={caps['geo']['shapely']} "
              f"anthropic={caps['vision']['anthropic_sdk']}")

        r = await c.get("/openapi.json")
        check("OpenAPI schema", r.status_code == 200,
              f"{len(r.json().get('paths', {}))} paths documented")

        # ------------------------------------------------------------ auth --
        tokens: dict[str, str] = {}
        for username, expected_role in [
            ("admin", "admin"),
            ("officer.sharma", "officer"),
            ("senior.iyer", "senior_officer"),
            ("citizen.priya", "consumer"),
            ("brand.parle", "brand"),
        ]:
            r = await c.post("/api/auth/login",
                             json={"username": username, "password": DEMO_PASSWORD})
            ok = r.status_code == 200 and r.json()["user"]["role"] == expected_role
            if ok:
                tokens[username] = r.json()["access_token"]
            check(f"login {username}", ok,
                  f"role={r.json().get('user', {}).get('role') if r.status_code == 200 else r.status_code}")

        # login by email
        r = await c.post("/api/auth/login",
                         json={"username": "officer.sharma@lm.gov.in", "password": DEMO_PASSWORD})
        check("login by email", r.status_code == 200)

        # wrong password must fail
        r = await c.post("/api/auth/login",
                         json={"username": "admin", "password": "wrong-password"})
        check("reject bad password", r.status_code == 401, f"got {r.status_code}")

        # ------------------------------------------------------------- me --
        r = await c.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {tokens['citizen.priya']}"})
        me = r.json()
        check("GET /api/auth/me", r.status_code == 200 and me["username"] == "citizen.priya",
              f"trust={me.get('citizen_trust_score')} badge={me.get('trust_badge')}")
        check("verified vigilant badge", me.get("trust_badge") == "VERIFIED_VIGILANT_CITIZEN",
              f"trust score {me.get('citizen_trust_score')} > 80")

        r = await c.get("/api/auth/me",
                        headers={"Authorization": f"Bearer {tokens['officer.sharma']}"})
        off = r.json()
        check("officer jurisdiction polygon",
              off.get("jurisdiction_geojson", {}).get("type") == "Polygon",
              off.get("jurisdiction_name", ""))

        # unauthenticated must be rejected
        r = await c.get("/api/auth/me")
        check("reject anonymous /me", r.status_code == 401, f"got {r.status_code}")

        r = await c.get("/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
        check("reject malformed token", r.status_code == 401, f"got {r.status_code}")

        # --------------------------------------------------------- refresh --
        r = await c.post("/api/auth/login",
                         json={"username": "officer.khan", "password": DEMO_PASSWORD})
        refresh = r.json()["refresh_token"]
        r = await c.post("/api/auth/refresh", json={"refresh_token": refresh})
        check("refresh token exchange", r.status_code == 200 and "access_token" in r.json())

        # a refresh token must NOT work as an access token
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
        check("refresh token rejected as access", r.status_code == 401, f"got {r.status_code}")

        # -------------------------------------------------------- register --
        # Registrations persist, so a fixed username is usable exactly once.
        uniq = secrets.token_hex(4)
        r = await c.post("/api/auth/register", json={
            "username": f"smoketest.{uniq}",
            "email": f"smoketest.{uniq}@example.com",
            "password": "Testing123",
            "full_name": "Smoke Test",
            "role": "consumer",
        })
        created = r.status_code == 201
        check("register consumer", created,
              f"trust={r.json()['user']['citizen_trust_score']}" if created else str(r.status_code))

        # duplicate username must conflict
        r = await c.post("/api/auth/register", json={
            "username": f"smoketest.{uniq}",
            "email": f"other.{uniq}@example.com",
            "password": "Testing123",
            "role": "consumer",
        })
        check("reject duplicate username", r.status_code == 409, f"got {r.status_code}")

        # self-registering as an officer must be rejected by the schema
        r = await c.post("/api/auth/register", json={
            "username": f"fake.officer.{uniq}",
            "email": f"fake.{uniq}@example.com",
            "password": "Testing123",
            "role": "officer",
        })
        check("reject officer self-registration", r.status_code == 422, f"got {r.status_code}")

    # ------------------------------------------------------------- report --
    width = max(len(n) for _s, n, _d in results)
    print("\n" + "=" * 78)
    print("  PHASE 0 SMOKE TEST")
    print("=" * 78)
    for statusv, name, detail in results:
        mark = "+" if statusv == PASS else "x"
        print(f"  [{mark}] {name:<{width}}  {detail}")
    failed = sum(1 for s, _n, _d in results if s == FAIL)
    print("=" * 78)
    print(f"  {len(results) - failed}/{len(results)} passed"
          + (f", {failed} FAILED" if failed else ""))
    print("=" * 78 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
