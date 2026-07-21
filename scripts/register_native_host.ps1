[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-p]{32}$')]
    [string[]]$ExtensionId,

    [ValidateSet('Chrome', 'Edge', 'Both')]
    [string]$Browser = 'Both',

    [string]$HostPath = (Join-Path $PSScriptRoot '..\dist\Reweave\ReweaveNativeHost.exe')
)

$ErrorActionPreference = 'Stop'
$resolvedHostPath = (Resolve-Path -LiteralPath $HostPath).Path
$dataRoot = if ($env:REWEAVE_DATA_DIR) {
    [System.IO.Path]::GetFullPath($env:REWEAVE_DATA_DIR)
} else {
    Join-Path $env:LOCALAPPDATA 'Reweave'
}
$manifestDirectory = Join-Path $dataRoot 'native-messaging'
$manifestPath = Join-Path $manifestDirectory 'com.reweave.bridge.json'
$allowedOrigins = @($ExtensionId | ForEach-Object { "chrome-extension://$_/" })

New-Item -ItemType Directory -Force -Path $manifestDirectory | Out-Null
[ordered]@{
    name = 'com.reweave.bridge'
    description = 'Reweave local extension bridge'
    path = $resolvedHostPath
    type = 'stdio'
    allowed_origins = $allowedOrigins
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

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
    New-Item -Force -Path $registryPath | Out-Null
    Set-Item -LiteralPath $registryPath -Value $manifestPath
}

[pscustomobject]@{
    Host = $resolvedHostPath
    Manifest = $manifestPath
    Browsers = $Browser
    AllowedOrigins = $allowedOrigins -join ', '
}
