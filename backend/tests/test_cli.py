import pytest
from sqlalchemy import select

from app import cli
from app.models import User
from app.security import verify_password
from tests.conftest import PASSWORD


@pytest.fixture
def prompts(monkeypatch):
    """Feed answers to getpass.getpass in order, and make sure the env shortcut is off."""
    monkeypatch.delenv("LIME_USER_PASSWORD", raising=False)

    def set_answers(*answers):
        it = iter(answers)
        monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(it))

    return set_answers


def password_hash(session_factory, email):
    with session_factory() as db:
        return db.scalar(select(User.password_hash).where(User.email == email))


def test_set_password_changes_login(client, session_factory, prompts, capsys):
    prompts("brand-new-pass", "brand-new-pass")
    cli.set_password("Admin@Lime-Ops.de", session_factory=session_factory)  # case doesn't matter
    assert "Password updated for admin@lime-ops.de" in capsys.readouterr().out
    assert verify_password("brand-new-pass", password_hash(session_factory, "admin@lime-ops.de"))

    login = lambda pw: client.post("/api/auth/login", json={"email": "admin@lime-ops.de", "password": pw})
    assert login("brand-new-pass").status_code == 200
    assert login(PASSWORD).status_code == 401


@pytest.mark.parametrize("answers,message", [
    (("brand-new-pass", "brand-new-typo"), "don't match"),
    (("short", "short"), "at least 8 characters"),
])
def test_set_password_rejects_bad_input_without_changes(session_factory, prompts, answers, message):
    before = password_hash(session_factory, "admin@lime-ops.de")
    prompts(*answers)
    with pytest.raises(SystemExit) as exc:
        cli.set_password("admin@lime-ops.de", session_factory=session_factory)
    assert message in str(exc.value) and "Nothing was changed" in str(exc.value)
    assert password_hash(session_factory, "admin@lime-ops.de") == before


def test_set_password_unknown_user_lists_existing(session_factory, prompts):
    prompts("brand-new-pass", "brand-new-pass")
    with pytest.raises(SystemExit) as exc:
        cli.set_password("nobody@lime-ops.de", session_factory=session_factory)
    assert "No user nobody@lime-ops.de" in str(exc.value)
    assert "admin@lime-ops.de" in str(exc.value) and "manager@lime-ops.de" in str(exc.value)


def test_set_password_from_env_skips_prompt(session_factory, monkeypatch):
    monkeypatch.setenv("LIME_USER_PASSWORD", "scripted-pass-1")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": pytest.fail("should not prompt"))
    cli.set_password("manager@lime-ops.de", session_factory=session_factory)
    assert verify_password("scripted-pass-1", password_hash(session_factory, "manager@lime-ops.de"))
