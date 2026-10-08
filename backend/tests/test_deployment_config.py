"""
Phase 7 — deployment configuration audit as tests: the production compose file, Dockerfiles and repository hygiene
must keep the security properties (internal-only infrastructure, non-root, no secrets, pinned images).
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]


def test_postgres_and_kafka_are_not_published_and_are_internal_only():
    for name in ("postgres", "kafka", "migrate", "scheduler"):
        assert "ports" not in SERVICES[name], f"{name} must not publish ports"
    assert SERVICES["postgres"]["networks"] == ["internal"] and SERVICES["kafka"]["networks"] == ["internal"]
    assert COMPOSE["networks"]["internal"]["internal"] is True  # no route to the outside world


def test_only_frontend_and_api_are_published_and_only_on_loopback():
    published = {n: s["ports"] for n, s in SERVICES.items() if "ports" in s}
    assert set(published) == {"api", "frontend"}
    for ports in published.values():
        assert all(p.startswith("127.0.0.1:") for p in ports), ports  # the TLS reverse proxy is the public entry point


def test_no_secret_literals_in_the_compose_file():
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert not re.search(r"gsk_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{16,}", text)
    for name, svc in SERVICES.items():
        env = svc.get("environment") or {}
        for key, value in (env.items() if isinstance(env, dict) else []):
            if re.search(r"PASSWORD|SECRET|API_KEY|DATABASE_URL", key) and value:
                assert "${" in str(value), f"{name}.{key} must come from the environment, not a literal"


def test_required_secrets_fail_loudly_when_missing():
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for var in ("JWT_SECRET", "APP_DB_PASSWORD", "POSTGRES_OWNER_PASSWORD", "PUBLIC_APP_ORIGIN", "LLM_PROVIDER"):
        assert f"${{{var}:?" in text, f"{var} must be required (${{VAR:?message}})"


def test_images_are_pinned_not_latest():
    for name, svc in SERVICES.items():
        image = svc.get("image", "")
        assert not image.endswith(":latest") and ":" in image, f"{name}: pin the image ({image})"


def test_services_restart_and_are_hardened():
    for name in ("postgres", "kafka", "api", "scheduler", "frontend"):
        assert SERVICES[name]["restart"] == "unless-stopped"
    for name in ("api", "scheduler", "frontend", "migrate"):
        s = SERVICES[name]
        assert s["read_only"] is True and s["cap_drop"] == ["ALL"] and "no-new-privileges:true" in s["security_opt"]
    for name in ("postgres", "kafka", "api", "frontend"):
        assert SERVICES[name]["healthcheck"]["test"], name
    assert SERVICES["migrate"]["restart"] == "no"  # deliberate one-shot: migrations never run implicitly on API start
    assert SERVICES["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"


def test_production_environment_is_forced_and_cookie_is_secure():
    env = SERVICES["api"]["environment"]
    assert env["ENVIRONMENT"] == "production" and env["COOKIE_SECURE"] == "true"
    assert "hivemind_app" in env["DATABASE_URL"]                              # the API uses the unprivileged role...
    assert "hivemind_owner" in SERVICES["migrate"]["environment"]["DATABASE_URL"]  # ...only migrations use the owner


def test_liveness_check_does_not_depend_on_downstream_services():
    test = " ".join(SERVICES["api"]["healthcheck"]["test"])
    assert "/health/live" in test and "/health/ready" not in test


def test_frontend_build_args_are_public_urls_only():
    args = SERVICES["frontend"]["build"]["args"]
    assert set(args) == {"NEXT_PUBLIC_API_ORIGIN", "NEXT_PUBLIC_WS_ORIGIN"}
    assert not any(re.search(r"KEY|SECRET|PASSWORD|TOKEN", k) for k in args)


@pytest.mark.parametrize("dockerfile", ["backend/Dockerfile", "frontend/Dockerfile"])
def test_dockerfiles_run_as_a_non_root_user_and_copy_no_secrets(dockerfile):
    text = (ROOT / dockerfile).read_text(encoding="utf-8")
    users = re.findall(r"^USER\s+(\S+)", text, re.MULTILINE)
    assert users and users[-1] not in ("root", "0", "0:0"), "the final stage must drop root"
    assert not re.search(r"COPY\s+.*\.env", text) and "ADD http" not in text
    assert re.search(r"^FROM\s+\S+:\S+", text, re.MULTILINE) and ":latest" not in text


@pytest.mark.parametrize("ctx", ["backend", "frontend"])
def test_dockerignore_keeps_secrets_and_local_state_out_of_images(ctx):
    lines = (ROOT / ctx / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines and ".env.*" in lines
    assert ("__pycache__/" if ctx == "backend" else "node_modules/") in lines


def test_backend_dependencies_are_pinned_by_constraints_for_deterministic_installs():
    constraints = (ROOT / "backend" / "constraints.txt").read_text(encoding="utf-8")
    assert re.search(r"(?im)^pyjwt==", constraints) and re.search(r"(?im)^argon2-cffi==", constraints)
    assert "RUN pip install -r requirements.txt -c constraints.txt" in (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")


def test_env_templates_hold_placeholders_only_and_real_env_files_are_git_ignored():
    for name in (".env.example", ".env.production.example"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"gsk_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{16,}|BEGIN [A-Z ]*PRIVATE KEY", text)
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert ".env" in ignored and ".env.production" in ignored


def test_the_postgres_init_script_creates_a_non_superuser_application_role():
    sh = (ROOT / "infra" / "postgres" / "init-app-role.sh").read_text(encoding="utf-8")
    assert "NOSUPERUSER" in sh and "NOCREATEROLE" in sh and "PASSWORD :'app_password'" in sh
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in sh and "GRANT ALL" not in sh.upper()
    assert not re.search(r"(?<!NO)SUPERUSER|CREATE\s+ON\s+SCHEMA public TO", sh)  # never a superuser, never DDL rights


def test_no_wildcard_cors_or_debug_mode_in_runtime_code():
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert 'allow_origins=["*"]' not in text and "debug=True" not in text, path
