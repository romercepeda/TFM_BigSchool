"""Unit tests for D11 — Roles & Permissions catalog validation.

Covers the pure Pydantic validation layer in app.roles.seed_loader.RolesCatalog:
shape checks that must fail fast per D11 §3 / Changeset C02 §1 acceptance criteria
("if the YAML file is missing or malformed, startup fails with a clear error").

The DB upsert behavior (insert / update / soft-deactivate / role_permissions refresh)
mirrors the D05 indicator-catalog loader, which has no dedicated DB-integration test
in this codebase either (test_d05_indicators.py covers only its pure calculators) —
consistent with that precedent, it is verified manually against the running stack.
"""

import pytest
import yaml
from pydantic import ValidationError

from app.roles.seed_loader import _CATALOG_PATH, RolesCatalog


def _catalog(**overrides: object) -> dict:
    """A minimal, valid two-permission/two-role catalog, overridable per test."""
    base = {
        "permissions": [
            {"code": "portfolio.list", "name_key": "permission.portfolio.list.name",
             "description_key": "permission.portfolio.list.description"},
            {"code": "user.list", "name_key": "permission.user.list.name",
             "description_key": "permission.user.list.description"},
        ],
        "roles": [
            {"code": "administrator", "name_key": "role.administrator.name",
             "description_key": "role.administrator.description",
             "is_default": False, "is_admin_role": True,
             "permissions": ["portfolio.list", "user.list"]},
            {"code": "investor", "name_key": "role.investor.name",
             "description_key": "role.investor.description",
             "is_default": True, "is_admin_role": False,
             "permissions": ["portfolio.list"]},
        ],
    }
    base.update(overrides)
    return base


class TestRolesCatalogValidation:
    def test_valid_catalog_parses(self) -> None:
        catalog = RolesCatalog.model_validate(_catalog())
        assert len(catalog.permissions) == 2
        assert len(catalog.roles) == 2

    def test_duplicate_permission_code_rejected(self) -> None:
        data = _catalog()
        data["permissions"].append(dict(data["permissions"][0]))
        with pytest.raises(ValidationError, match="duplicate permission code"):
            RolesCatalog.model_validate(data)

    def test_duplicate_role_code_rejected(self) -> None:
        data = _catalog()
        data["roles"].append(dict(data["roles"][0]))
        with pytest.raises(ValidationError, match="duplicate role code"):
            RolesCatalog.model_validate(data)

    def test_zero_default_roles_rejected(self) -> None:
        data = _catalog()
        data["roles"][1]["is_default"] = False
        with pytest.raises(ValidationError, match="is_default"):
            RolesCatalog.model_validate(data)

    def test_two_default_roles_rejected(self) -> None:
        data = _catalog()
        data["roles"][0]["is_default"] = True
        with pytest.raises(ValidationError, match="is_default"):
            RolesCatalog.model_validate(data)

    def test_zero_admin_roles_rejected(self) -> None:
        data = _catalog()
        data["roles"][0]["is_admin_role"] = False
        with pytest.raises(ValidationError, match="is_admin_role"):
            RolesCatalog.model_validate(data)

    def test_two_admin_roles_rejected(self) -> None:
        data = _catalog()
        data["roles"][1]["is_admin_role"] = True
        with pytest.raises(ValidationError, match="is_admin_role"):
            RolesCatalog.model_validate(data)

    def test_role_referencing_unknown_permission_rejected(self) -> None:
        data = _catalog()
        data["roles"][1]["permissions"].append("does.not_exist")
        with pytest.raises(ValidationError, match="unknown permission code"):
            RolesCatalog.model_validate(data)

    def test_missing_required_field_rejected(self) -> None:
        data = _catalog()
        del data["roles"][0]["is_admin_role"]
        with pytest.raises(ValidationError):
            RolesCatalog.model_validate(data)


class TestRealCatalogFile:
    """Golden-file check: the actual roles_catalog.yaml must always validate cleanly."""

    def test_real_catalog_file_is_valid(self) -> None:
        assert _CATALOG_PATH.exists(), f"{_CATALOG_PATH} not found"
        with open(_CATALOG_PATH) as f:
            raw = yaml.safe_load(f)
        catalog = RolesCatalog.model_validate(raw)
        assert len(catalog.roles) == 2
        admin_role = next(r for r in catalog.roles if r.is_admin_role)
        investor_role = next(r for r in catalog.roles if r.is_default)
        assert admin_role.code == "administrator"
        assert investor_role.code == "investor"
        # Administrator must hold every permission in the catalog (D11 §5.2).
        all_codes = {p.code for p in catalog.permissions}
        assert set(admin_role.permissions) == all_codes
        # Investor must not hold any admin-scope user.*/role.*/system.* permission,
        # except the explicit own-data exception user.change_own_password (D11 §5.2).
        forbidden_prefixes = ("user.", "role.", "system.")
        leaked = [
            c for c in investor_role.permissions
            if c.startswith(forbidden_prefixes) and c != "user.change_own_password"
        ]
        assert leaked == [], f"investor role must not hold admin-scope permissions: {leaked}"
        assert "user.change_own_password" in investor_role.permissions
