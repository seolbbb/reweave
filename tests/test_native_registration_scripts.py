"""Run unregistration against mocked Registry operations and isolated manifest files."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "unregister_native_host.ps1"
KEYS = {
    "Chrome": r"HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.reweave.bridge",
    "Edge": r"HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.reweave.bridge",
}

# Every provider call the production script can make is shadowed before invocation.
# Native cmdlets are delegated only for explicitly checked temporary filesystem paths.
HARNESS = r"""
param([string]$ConfigPath, [string]$ScriptPath)
$ErrorActionPreference = 'Stop'
$config = Microsoft.PowerShell.Management\Get-Content -LiteralPath $ConfigPath -Raw |
    ConvertFrom-Json
$global:MockRoot = [System.IO.Path]::GetFullPath($config.root)
$global:MockManifest = [System.IO.Path]::GetFullPath($config.manifest)
$global:MockRegistry = @{}
foreach ($property in $config.registry.PSObject.Properties) {
    $global:MockRegistry[$property.Name] = $property.Value
}
$global:MockRemoved = [System.Collections.Generic.List[string]]::new()
$global:MockInvalidName = $config.invalid_name
$global:MockReparse = $config.reparse
$global:MockAllowed = @(
    'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.reweave.bridge',
    'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.reweave.bridge'
)
function Test-MockRegistryPath([string]$Value) {
    if ($Value -match '^(HK[A-Z]+:|Registry::|Microsoft\.PowerShell\.Core\\Registry::|HKEY_)') {
        if ($global:MockAllowed -notcontains $Value) { throw 'REGISTRY TRIPWIRE: unexpected key' }
        return $true
    }
    return $false
}
function Assert-MockFile([string]$Value) {
    $resolved = [System.IO.Path]::GetFullPath($Value)
    $inside = $resolved.StartsWith(
        $global:MockRoot + '\', [System.StringComparison]::OrdinalIgnoreCase
    )
    if (-not $inside) {
        throw 'FILESYSTEM TRIPWIRE: outside synthetic root'
    }
}
function Test-Path {
    param([string]$LiteralPath)
    if (Test-MockRegistryPath $LiteralPath) {
        return $global:MockRegistry.ContainsKey($LiteralPath)
    }
    Assert-MockFile $LiteralPath
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
function Get-Item {
    param([string]$LiteralPath)
    if (Test-MockRegistryPath $LiteralPath) {
        if (-not $global:MockRegistry.ContainsKey($LiteralPath)) { throw 'Missing synthetic key' }
        $name = $LiteralPath.Replace('HKCU:\', 'HKEY_CURRENT_USER\')
        if ($global:MockInvalidName) { $name = 'HKEY_CURRENT_USER\Software\Foreign' }
        $item = [pscustomobject]@{ Name=$name; Target=$global:MockRegistry[$LiteralPath] }
        return ($item | Add-Member -MemberType ScriptMethod -Name GetValue -Value {
            param($Name)
            if ($Name -ne '') { throw 'Unexpected registry value read' }
            return $this.Target
        } -PassThru)
    }
    Assert-MockFile $LiteralPath
    $file = Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath
    if ($global:MockReparse) {
        return [pscustomobject]@{
            FullName=$file.FullName; Length=$file.Length; PSIsContainer=$false;
            Attributes=[System.IO.FileAttributes]::ReparsePoint }
    }
    return $file
}
function Get-Content {
    param([string]$LiteralPath, [switch]$Raw)
    if (Test-MockRegistryPath $LiteralPath) { throw 'REGISTRY TRIPWIRE: content read' }
    Assert-MockFile $LiteralPath
    return Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw:$Raw
}
function Remove-Item {
    param([string]$LiteralPath, [switch]$Recurse)
    if (Test-MockRegistryPath $LiteralPath) {
        if (-not $Recurse) { throw 'Unexpected registry removal mode' }
        $global:MockRemoved.Add($LiteralPath)
        $global:MockRegistry.Remove($LiteralPath)
        return
    }
    Assert-MockFile $LiteralPath
    if ($Recurse -or $LiteralPath -ne $global:MockManifest) {
        throw 'FILESYSTEM TRIPWIRE: unexpected deletion'
    }
    Microsoft.PowerShell.Management\Remove-Item -LiteralPath $LiteralPath
}
function Get-ItemProperty { throw 'REGISTRY TRIPWIRE: unexpected operation' }
function Set-Item { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function Set-ItemProperty { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function New-Item { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function New-ItemProperty { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function Remove-ItemProperty { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function Rename-Item { throw 'REGISTRY TRIPWIRE: unexpected mutation' }
function Get-ChildItem { throw 'REGISTRY TRIPWIRE: unexpected enumeration' }
$env:REWEAVE_DATA_DIR = $config.data
$failure = $null
$result = $null
try { $result = & $ScriptPath -Browser $config.browser } catch { $failure = $_.Exception.Message }
[ordered]@{
    error=$failure; result=$result; removed=@($global:MockRemoved); remaining=$global:MockRegistry;
    manifest_exists=(Microsoft.PowerShell.Management\Test-Path -LiteralPath $global:MockManifest)
} | ConvertTo-Json -Depth 8 -Compress
"""


def invoke(tmp_path, browser="Both", *, references=None, manifest_kind="owned", **options):
    if os.name != "nt":
        pytest.skip("Windows PowerShell isolated Registry mock")
    data = tmp_path / "data"
    manifest = data / "native-messaging" / "com.reweave.bridge.json"
    manifest.parent.mkdir(parents=True)
    value = {
        "name": "com.reweave.bridge",
        "description": "Reweave local extension bridge",
        "path": str(tmp_path / "synthetic-program" / "ReweaveNativeHost.exe"),
        "type": "stdio",
        "allowed_origins": ["chrome-extension://" + "a" * 32 + "/"],
    }
    if manifest_kind == "foreign":
        value["name"] = "com.foreign.bridge"
    if manifest_kind == "foreign-origin":
        value["allowed_origins"] = ["chrome-extension://not-an-exact-id/"]
    if manifest_kind != "missing":
        manifest.write_text("invalid JSON" if manifest_kind == "malformed" else json.dumps(value))
    foreign = tmp_path / "foreign-manifest.json"
    foreign.write_text("foreign manifest sentinel")
    refs = references if references is not None else {"Chrome": "owned", "Edge": "owned"}
    registry = {
        KEYS[name]: str(manifest if destination == "owned" else foreign)
        for name, destination in refs.items()
    }
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "root": str(tmp_path),
                "data": str(data),
                "manifest": str(manifest),
                "browser": browser,
                "registry": registry,
                **options,
            }
        )
    )
    harness = tmp_path / "harness.ps1"
    harness.write_text(HARNESS, encoding="utf-8-sig")
    process = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
            "-ConfigPath",
            str(config),
            "-ScriptPath",
            str(SCRIPT),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert process.returncode == 0, process.stderr
    assert foreign.read_text() == "foreign manifest sentinel"
    return json.loads(process.stdout), manifest


@pytest.mark.parametrize("browser,other", [("Chrome", "Edge"), ("Edge", "Chrome")])
def test_partial_unregistration_preserves_other_browser_and_shared_manifest(
    tmp_path, browser, other
):
    result, _ = invoke(tmp_path, browser)
    assert result["error"] is None
    assert result["removed"] == [KEYS[browser]]
    assert set(result["remaining"]) == {KEYS[other]}
    assert result["manifest_exists"] and result["result"]["ManifestRetained"]
    assert not result["result"]["ManifestRemoved"]


def test_both_removes_exact_owned_entries_and_manifest(tmp_path):
    result, _ = invoke(tmp_path)
    assert result["error"] is None
    assert set(result["removed"]) == set(KEYS.values())
    assert result["remaining"] == {} and not result["manifest_exists"]
    assert result["result"]["ManifestRemoved"] and result["result"]["Removed"]


@pytest.mark.parametrize("browser", ["Chrome", "Edge"])
def test_last_registered_browser_removes_manifest(tmp_path, browser):
    result, _ = invoke(tmp_path, browser, references={browser: "owned"})
    assert result["error"] is None and result["removed"] == [KEYS[browser]]
    assert not result["manifest_exists"]


def test_foreign_registration_and_foreign_file_remain(tmp_path):
    result, _ = invoke(tmp_path, references={"Chrome": "owned", "Edge": "foreign"})
    assert result["error"] is None and result["removed"] == [KEYS["Chrome"]]
    assert set(result["remaining"]) == {KEYS["Edge"]}
    assert not result["manifest_exists"]


@pytest.mark.parametrize("kind", ["foreign", "foreign-origin", "malformed"])
def test_foreign_or_unrecognized_manifest_and_its_registrations_remain(tmp_path, kind):
    result, manifest = invoke(tmp_path, manifest_kind=kind)
    assert result["error"] is None and result["removed"] == []
    assert set(result["remaining"]) == set(KEYS.values())
    assert result["manifest_exists"] and manifest.exists()


def test_missing_manifest_allows_exact_orphan_registration_cleanup(tmp_path):
    result, _ = invoke(tmp_path, manifest_kind="missing")
    assert result["error"] is None and set(result["removed"]) == set(KEYS.values())
    assert not result["manifest_exists"]


def test_unrecognized_resolved_registry_name_stops_before_any_removal(tmp_path):
    result, _ = invoke(tmp_path, invalid_name=True)
    assert "outside its exact owned key" in result["error"]
    assert result["removed"] == [] and result["manifest_exists"]


def test_redirected_manifest_is_preserved(tmp_path):
    result, _ = invoke(tmp_path, reparse=True)
    assert result["error"] is None and result["removed"] == []
    assert result["manifest_exists"]


def test_valid_unreferenced_manifest_can_be_removed_without_registry_mutation(tmp_path):
    result, _ = invoke(tmp_path, references={})
    assert result["error"] is None and result["removed"] == []
    assert not result["manifest_exists"]
