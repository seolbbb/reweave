[CmdletBinding()]
param(
    [ValidateSet('Chrome', 'Edge', 'Both')]
    [string]$Browser = 'Both'
)

$ErrorActionPreference = 'Stop'
$dataRoot = if ($env:REWEAVE_DATA_DIR) {
    [System.IO.Path]::GetFullPath($env:REWEAVE_DATA_DIR)
} else {
    Join-Path $env:LOCALAPPDATA 'Reweave'
}
$manifestPath = [System.IO.Path]::GetFullPath(
    (Join-Path $dataRoot 'native-messaging\com.reweave.bridge.json')
)
$registryPaths = @{
    Chrome = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.reweave.bridge'
    Edge = 'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.reweave.bridge'
}

function Test-ExpectedManifestReference {
    param($Value)
    if ($Value -isnot [string] -or -not [System.IO.Path]::IsPathRooted($Value)) {
        return $false
    }
    try {
        return [System.IO.Path]::GetFullPath($Value).Equals(
            $manifestPath, [System.StringComparison]::OrdinalIgnoreCase
        )
    } catch { return $false }
}

function Get-BridgeRegistration {
    param([string]$RegistryPath)
    if (-not (Test-Path -LiteralPath $RegistryPath)) { return $null }
    $entry = Get-Item -LiteralPath $RegistryPath
    $expectedName = $RegistryPath.Replace('HKCU:\', 'HKEY_CURRENT_USER\')
    if ($entry.Name -ine $expectedName) {
        throw 'Native Messaging registration resolved outside its exact owned key.'
    }
    return $entry
}

function Test-OwnedManifest {
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $false }
    try {
        $file = Get-Item -LiteralPath $manifestPath
        if ($file.PSIsContainer -or $file.Length -gt 65536 -or
            -not $file.FullName.Equals($manifestPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }
        # A redirected file or parent could belong to a different installation.
        $part = $file
        while ($null -ne $part) {
            if ($part.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { return $false }
            $part = if ($part -is [System.IO.FileInfo]) { $part.Directory } else { $part.Parent }
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.name -ne 'com.reweave.bridge' -or $manifest.type -ne 'stdio' -or
            $manifest.description -ne 'Reweave local extension bridge' -or
            $manifest.path -isnot [string] -or -not [System.IO.Path]::IsPathRooted($manifest.path)) {
            return $false
        }
        $origins = @($manifest.allowed_origins)
        return $origins.Count -gt 0 -and @(
            $origins | Where-Object { $_ -isnot [string] -or $_ -notmatch '^chrome-extension://[a-p]{32}/$' }
        ).Count -eq 0
    } catch { return $false }
}

$manifestExists = Test-Path -LiteralPath $manifestPath
$manifestOwned = Test-OwnedManifest
$selectedBrowsers = if ($Browser -eq 'Both') { @('Chrome', 'Edge') } else { @($Browser) }
$removedBrowsers = @()
foreach ($selectedBrowser in $selectedBrowsers) {
    $registryPath = $registryPaths[$selectedBrowser]
    $entry = Get-BridgeRegistration -RegistryPath $registryPath
    if ($null -ne $entry -and (Test-ExpectedManifestReference $entry.GetValue('')) -and
        (-not $manifestExists -or $manifestOwned)) {
        # Get-BridgeRegistration checked the absolute registry name immediately above.
        Remove-Item -LiteralPath $registryPath -Recurse
        $removedBrowsers += $selectedBrowser
    }
}

$remainingReference = $false
foreach ($registryPath in $registryPaths.Values) {
    $entry = Get-BridgeRegistration -RegistryPath $registryPath
    if ($null -ne $entry -and (Test-ExpectedManifestReference $entry.GetValue(''))) {
        $remainingReference = $true
    }
}
$manifestRemoved = $false
if (-not $remainingReference -and (Test-OwnedManifest)) {
    Remove-Item -LiteralPath $manifestPath
    $manifestRemoved = $true
}

[pscustomobject]@{
    Manifest = $manifestPath
    Browsers = $Browser
    Removed = $true
    RegistrationsRemoved = $removedBrowsers
    ManifestRemoved = $manifestRemoved
    ManifestRetained = (Test-Path -LiteralPath $manifestPath)
}
