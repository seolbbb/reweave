"""Manifest V3 extension scaffold safety tests."""

from __future__ import annotations

import json
from pathlib import Path

EXTENSION_DIR = Path(__file__).parents[1] / "extension"


def test_manifest_is_permission_minimal_and_has_no_page_access():
    manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["permissions"] == ["nativeMessaging"]
    assert "host_permissions" not in manifest
    assert "optional_host_permissions" not in manifest
    assert "content_scripts" not in manifest
    assert manifest["background"] == {"service_worker": "background.js"}
    assert manifest["action"]["default_popup"] == "popup.html"


def test_extension_scaffold_only_requests_the_availability_protocol():
    background = (EXTENSION_DIR / "background.js").read_text(encoding="utf-8")
    popup = (EXTENSION_DIR / "popup.js").read_text(encoding="utf-8")

    assert 'const NATIVE_HOST = "com.reweave.bridge"' in background
    assert 'type: "ping"' in background
    assert "fetch(" not in background
    assert "tabs" not in background
    assert "querySelector" not in background
    assert "Save and Use actions will be added next" in popup


def test_popup_exposes_accessible_actionable_states():
    html = (EXTENSION_DIR / "popup.html").read_text(encoding="utf-8")
    css = (EXTENSION_DIR / "popup.css").read_text(encoding="utf-8")

    assert 'aria-live="polite"' in html
    assert '<button id="retry" type="button"' in html
    assert "min-height: 44px" in css
    assert "prefers-color-scheme: dark" in css
    assert "prefers-reduced-motion: reduce" in css
