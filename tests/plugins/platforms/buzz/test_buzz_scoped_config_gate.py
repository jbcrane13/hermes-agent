"""Scoped Buzz startup accepts canonical platform config without identity leakage."""

import os

import hermes_yaml as yaml
import pytest

from agent.secret_scope import (
    reset_secret_scope,
    set_multiplex_active,
    set_secret_scope,
)
from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from plugins.platforms.buzz.adapter import check_requirements


def test_scoped_gate_reads_top_level_config_across_profiles(tmp_path, monkeypatch):
    """A configured secondary starts; its neighbour cannot borrow its configuration."""
    configured = tmp_path / "configured"
    empty = tmp_path / "empty"
    configured.mkdir()
    empty.mkdir()
    (configured / "config.yaml").write_text(yaml.safe_dump({
        "platforms": {"buzz": {"enabled": True, "extra": {
            "relay_url": "https://secondary.example.invalid",
        }}},
    }))
    (empty / "config.yaml").write_text("{}\n")
    monkeypatch.setenv("BUZZ_RELAY_URL", "https://launch.example.invalid")
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "not-a-real-launch-key")
    env_before = dict(os.environ)
    set_multiplex_active(True)
    try:
        for home, secrets, expected in (
            (configured, {"BUZZ_PRIVATE_KEY": "not-a-real-secondary-key"}, True),
            (empty, {"BUZZ_PRIVATE_KEY": "not-a-real-secondary-key"}, False),
            (configured, {}, False),
            (configured, {"BUZZ_PRIVATE_KEY": "not-a-real-secondary-key"}, True),
        ):
            home_token = set_hermes_home_override(str(home))
            secret_token = set_secret_scope(secrets)
            try:
                assert check_requirements() is expected
            finally:
                reset_secret_scope(secret_token)
                reset_hermes_home_override(home_token)
        assert dict(os.environ) == env_before
    finally:
        set_multiplex_active(False)


@pytest.mark.parametrize("layout,expected", [
    ("legacy_nested", True),
    ("gateway_subsection", True),
    ("bare_platform", True),
    ("split_extra", True),
    ("canonical_clear", False),
    ("scoped_expansion", True),
])
def test_scoped_gate_uses_gateway_composition(tmp_path, layout, expected):
    import json

    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"private_key": "not-a-real-test-key"}))
    relay = {"relay_url": "https://profile.example.invalid"}
    key = {"credentials_file": str(credentials)}
    combined = {**relay, **key}
    layouts = {
        "legacy_nested": {"gateway": {"platforms": {"buzz": {"extra": combined}}}},
        "gateway_subsection": {"gateway": {"buzz": {"extra": combined}}},
        "bare_platform": {"platforms": {"buzz": combined}},
        "split_extra": {
            "gateway": {"platforms": {"buzz": {"extra": key}}},
            "platforms": {"buzz": {"extra": relay}},
        },
        "canonical_clear": {
            "gateway": {"platforms": {"buzz": {"extra": combined}}},
            "platforms": {"buzz": {"extra": {"relay_url": ""}}},
        },
        "scoped_expansion": {"platforms": {"buzz": {"extra": {
            **key, "relay_url": "${TEST_BUZZ_RELAY}",
        }}}},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(layouts[layout]))
    home_token = set_hermes_home_override(str(tmp_path))
    secret_token = set_secret_scope({"TEST_BUZZ_RELAY": relay["relay_url"]})
    set_multiplex_active(True)
    try:
        assert check_requirements() is expected
    finally:
        reset_secret_scope(secret_token)
        reset_hermes_home_override(home_token)
        set_multiplex_active(False)
