import pytest
from pydantic import ValidationError

from app.config import Settings


def test_safe_pool_configuration_is_accepted():
    settings = Settings(
        _env_file=None,
        db_pool_size=2,
        db_max_overflow=0,
        db_connection_budget=2,
    )

    assert settings.db_pool_size + settings.db_max_overflow <= settings.db_connection_budget


def test_session_token_lifetime_defaults_to_thirty_days():
    settings = Settings(_env_file=None)

    assert settings.session_ttl_hours == 24 * 30


def test_backend_refuses_to_start_when_pool_exceeds_budget():
    with pytest.raises(ValidationError, match="DB_CONNECTION_BUDGET"):
        Settings(
            _env_file=None,
            db_pool_size=3,
            db_max_overflow=1,
            db_connection_budget=3,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_pool_size", 0),
        ("db_connection_budget", 0),
        ("db_pool_timeout", 0),
        ("db_max_overflow", -1),
    ],
)
def test_invalid_pool_values_are_rejected(field: str, value: int):
    values = {
        "db_pool_size": 2,
        "db_max_overflow": 0,
        "db_connection_budget": 2,
        field: value,
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_production_pool_of_five_is_accepted():
    settings = Settings(_env_file=None, db_pool_size=5, db_max_overflow=0, db_connection_budget=5)
    assert settings.db_pool_size == 5


def test_pool_of_six_exceeds_budget_of_five():
    with pytest.raises(ValidationError, match="DB_CONNECTION_BUDGET"):
        Settings(_env_file=None, db_pool_size=6, db_max_overflow=0, db_connection_budget=5)


def test_application_name_includes_instance():
    assert Settings(_env_file=None, app_instance="Dev").db_application_name == "billing_control:dev"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_instance="bad name!")


def test_auth_cache_is_off_by_default():
    assert Settings(_env_file=None).auth_cache_ttl_seconds == 0
