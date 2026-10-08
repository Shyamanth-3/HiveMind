"""Phase 7 — production configuration: unsafe settings fail startup clearly; development defaults never leak in."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import ConfigurationError, Settings
from app.core.kafka_config import kafka_security_config

BACKEND = Path(__file__).resolve().parents[1]
GOOD_DB = "postgresql+psycopg://hivemind_app:S0me-Str0ng-Db-Pass@db.internal:5432/hivemind"


def prod(**over) -> Settings:
    base = dict(_env_file=None, ENVIRONMENT="production", DATABASE_URL=GOOD_DB, JWT_SECRET="j" * 40, COOKIE_SECURE=True,
                CORS_ORIGINS="https://app.example.com", LLM_PROVIDER="groq", GROQ_API_KEY="k" * 30, LLM_MODEL="")
    base.update(over)
    return Settings(**base)


def test_a_complete_production_configuration_passes():
    prod().assert_production_ready()


@pytest.mark.parametrize("over,needle", [
    ({"JWT_SECRET": ""}, "JWT_SECRET"),
    ({"JWT_SECRET": "short"}, "JWT_SECRET"),
    ({"COOKIE_SECURE": False}, "COOKIE_SECURE"),
    ({"CORS_ORIGINS": "*"}, "wildcard"),
    ({"CORS_ORIGINS": "https://*.example.com"}, "wildcard"),
    ({"CORS_ORIGINS": "http://app.example.com"}, "https://"),
    ({"CORS_ORIGINS": "http://localhost:3000"}, "https://"),
    ({"CORS_ORIGINS": ""}, "CORS_ORIGINS"),
    ({"DATABASE_URL": "postgresql+psycopg://hivemind:password@db/hivemind"}, "non-default"),
    ({"DATABASE_URL": "postgresql+psycopg://postgres:Str0ng-Pass-12345@db/hivemind"}, "non-superuser"),
    ({"DATABASE_URL": "postgresql+psycopg://app@db/hivemind"}, "non-default"),
    ({"ACCESS_TOKEN_EXPIRE_MINUTES": 0}, "ACCESS_TOKEN_EXPIRE_MINUTES"),
    ({"ACCESS_TOKEN_EXPIRE_MINUTES": 100000}, "ACCESS_TOKEN_EXPIRE_MINUTES"),
    ({"GROQ_API_KEY": ""}, "GROQ_API_KEY"),
    ({"LLM_PROVIDER": "nope"}, "Unsupported LLM_PROVIDER"),
    ({"KAFKA_SECURITY_PROTOCOL": "SASL_SSL"}, "KAFKA_SASL"),
])
def test_unsafe_production_settings_fail_startup_with_a_clear_reason(over, needle):
    with pytest.raises(ConfigurationError) as e:
        prod(**over).assert_production_ready()
    assert needle in str(e.value)


def test_every_problem_is_reported_at_once_and_no_secret_value_is_printed():
    with pytest.raises(ConfigurationError) as e:
        prod(JWT_SECRET="", COOKIE_SECURE=False, CORS_ORIGINS="*", GROQ_API_KEY="gsk_topsecretvalue12345").assert_production_ready()
    msg = str(e.value)
    assert msg.count("\n - ") >= 3 and "topsecretvalue" not in msg and GOOD_DB.split(":")[2].split("@")[0] not in msg


def test_development_defaults_never_activate_in_production():
    s = Settings(_env_file=None, ENVIRONMENT="production", DATABASE_URL=GOOD_DB)
    assert s.JWT_SECRET == ""            # no generated / hard-coded fallback secret in production
    assert s.COOKIE_SECURE is False and s.is_production
    with pytest.raises(ConfigurationError):
        s.assert_production_ready()


def test_outside_production_a_random_per_process_secret_is_generated_never_a_constant():
    a = Settings(_env_file=None, DATABASE_URL=GOOD_DB)
    b = Settings(_env_file=None, DATABASE_URL=GOOD_DB)
    assert len(a.JWT_SECRET) >= 32 and a.JWT_SECRET != b.JWT_SECRET
    a.assert_production_ready()  # non-production: validation is a no-op


def test_invalid_environment_name_is_rejected():
    with pytest.raises(Exception):
        Settings(_env_file=None, ENVIRONMENT="prod", DATABASE_URL=GOOD_DB)


def test_kafka_security_settings_reach_both_clients_only_when_configured(monkeypatch):
    from app.core import kafka_config
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SECURITY_PROTOCOL", "")
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SASL_MECHANISM", "")
    assert kafka_security_config() == {}
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SASL_USERNAME", "hivemind")
    monkeypatch.setattr(kafka_config.settings, "KAFKA_SASL_PASSWORD", "pw")
    assert kafka_security_config() == {"security.protocol": "SASL_SSL", "sasl.mechanism": "SCRAM-SHA-512",
                                       "sasl.username": "hivemind", "sasl.password": "pw"}


def _run_app_module(code: str, **env) -> subprocess.CompletedProcess:
    full = {**os.environ, "DATABASE_URL": GOOD_DB, "GROQ_API_KEY": "k" * 30, "EMBEDDING_PROVIDER": "none", **env}
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=full, capture_output=True, text=True, timeout=120)


def test_api_docs_are_disabled_in_production_and_enabled_in_development():
    code = "from app.main import app; print(app.docs_url, app.redoc_url, app.openapi_url)"
    p = _run_app_module(code, ENVIRONMENT="production")
    d = _run_app_module(code, ENVIRONMENT="development")
    assert p.stdout.strip().splitlines()[-1] == "None None None"
    assert d.stdout.strip().splitlines()[-1] == "/docs /redoc /openapi.json"


def test_the_api_process_refuses_to_start_in_production_without_a_secret():
    code = ("import asyncio; from app.main import app, lifespan\n"
            "async def go():\n"
            "    async with lifespan(app): pass\n"
            "asyncio.run(go())")
    p = _run_app_module(code, ENVIRONMENT="production", JWT_SECRET="", CORS_ORIGINS="https://app.example.com", COOKIE_SECURE="true")
    assert p.returncode != 0 and "Unsafe production configuration" in p.stderr and "JWT_SECRET" in p.stderr
