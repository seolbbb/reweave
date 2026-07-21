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
$manifestPath = Join-Path $dataRoot 'native-messaging\com.reweave.bridge.json'
$registryRoots = switch ($Browser) {
    'Chrome' { @('HKCU:\Software\Google\Chrome\NativeMessagingHosts') }
    'Edge' { @('HKCU:\Software\Microsoft\Edge\NativeMessagingHosts') }
    'Both' {
        @(
            'HKCU:\Software\Google\Chrome\NativeMessagingHosts'
            'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts'
        )
    }
}

foreach ($registryRoot in $registryRoots) {
    $registryPath = Join-Path $registryRoot 'com.reweave.bridge'
    if (Test-Path -LiteralPath $registryPath) {
        Remove-Item -LiteralPath $registryPath -Recurse
    }
}

if (Test-Path -LiteralPath $manifestPath) {
    Remove-Item -LiteralPath $manifestPath
}

[pscustomobject]@{
    Manifest = $manifestPath
    Browsers = $Browser
    Removed = $true
}
