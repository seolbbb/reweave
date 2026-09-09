# File ownership is validated completely before modifying an installation.
# User archives, provider credentials, and Native Messaging registration are separate.
param(
    [Parameter(Mandatory = $true)][ValidateSet('Install', 'Uninstall')][string]$Operation,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [string]$PayloadRoot = '',
    [ValidateSet('0', '1')][string]$Isolated = '0',
    [string]$WorkspaceRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$productId = 'reweave-local-desktop-8912a075-3c88-4ec1-a542-2a6a228bb592'
$markerName = '.reweave-install.json'
$manifestName = '.reweave-files.json'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Reweave'

function Get-AbsolutePath([string]$Value) {
    if ($Value -notmatch '^[A-Za-z]:[\\/]' -or $Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw 'An absolute local drive path is required.'
    }
    foreach ($part in $Value.Substring(3).TrimEnd('\', '/').Split([char[]]@('\', '/'))) {
        if (!$part -or $part.EndsWith(' ') -or $part.EndsWith('.') -or $part -match '[<>:"|?*\x00-\x1f]' -or
            $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') {
            throw 'An unambiguous absolute Windows path is required.'
        }
    }
    return [IO.Path]::GetFullPath($Value).TrimEnd('\', '/')
}

function Assert-PlainPath([string]$Value) {
    $current = $Value
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $entry = Get-Item -Force -LiteralPath $current
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Links and junctions are not valid installation paths.'
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}

function Get-OwnedPath([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative.Contains('\') -or $Relative.StartsWith('/')) {
        throw 'Invalid relative path in file manifest.'
    }
    foreach ($part in $Relative.Split('/')) {
        if (!$part -or $part -eq '.' -or $part -eq '..' -or $part -match '[<>:"|?*\x00-\x1f]' -or
            $part.EndsWith(' ') -or $part.EndsWith('.') -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') {
            throw 'Unsafe Windows path in file manifest.'
        }
    }
    $full = Get-AbsolutePath (Join-Path $Root $Relative.Replace('/', '\'))
    if (!$full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Manifest path escapes the installation directory.'
    }
    Assert-PlainPath $full
    return $full
}

function Read-Json([string]$Path) {
    Assert-PlainPath $Path
    if (!(Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).Length -gt 12000000) {
        throw 'Installation metadata is missing or too large.'
    }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Read-Manifest([string]$Root) {
    $manifest = Read-Json (Join-Path $Root $manifestName)
    if ($manifest.schema -ne 1 -or $manifest.product -ne $productId -or @($manifest.files).Count -gt 30000 -or @($manifest.files).Count -lt 1) {
        throw 'Unsupported installation manifest.'
    }
    $seen = @{}
    foreach ($file in $manifest.files) {
        $null = Get-OwnedPath $Root $file.path
        if ($file.path -in @($markerName, $manifestName) -or $seen.ContainsKey($file.path) -or
            $file.sha256 -notmatch '^[0-9a-f]{64}$' -or $file.size -lt 0) {
            throw 'Invalid or duplicate manifest entry.'
        }
        $seen[$file.path] = $file
    }
    return $manifest
}

function Assert-Marker([string]$Root) {
    $marker = Read-Json (Join-Path $Root $markerName)
    if ($marker.schema -ne 1 -or $marker.product -ne $productId -or $marker.root -ne $Root -or
        $marker.isolated -ne $Isolated -or ($Isolated -eq '1' -and $marker.workspace -ne $script:workspace)) {
        throw 'This directory is not a matching Reweave installation.'
    }
    return $marker
}

function Get-FileDigest([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Test-MatchingFile([string]$Path, $Entry) {
    return ((Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-Item -LiteralPath $Path).Length -eq $Entry.size -and
        (Get-FileDigest $Path) -eq $Entry.sha256)
}

function Write-Json([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}

function Remove-EmptyOwnedDirectories([string]$Root, $Files) {
    $directories = @{}
    foreach ($file in $Files) {
        $directory = [IO.Path]::GetDirectoryName((Get-OwnedPath $Root $file.path))
        while ($directory -and $directory -ne $Root) {
            $directories[$directory] = $true
            $directory = [IO.Path]::GetDirectoryName($directory)
        }
    }
    foreach ($directory in ($directories.Keys | Sort-Object Length -Descending)) {
        Assert-PlainPath $directory
        if ((Test-Path -LiteralPath $directory -PathType Container) -and
            @(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
            # Never recurse: an unrelated file or directory must keep its parent.
            Remove-Item -LiteralPath $directory -Force
        }
    }
}

try {
    $root = Get-AbsolutePath $InstallRoot
    Assert-PlainPath $root
    $script:workspace = ''
    if ($Isolated -eq '1') {
        $script:workspace = Get-AbsolutePath $WorkspaceRoot
        Assert-PlainPath $script:workspace
        if (!(Test-Path -LiteralPath $script:workspace -PathType Container)) { throw 'The explicit QA workspace must exist.' }
        $boundary = Join-Path $script:workspace '.pytest_cache'
        if (!$root.StartsWith($boundary + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Isolated installation must be below the explicit workspace .pytest_cache directory.'
        }
    } else {
        $expected = Get-AbsolutePath (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Reweave')
        if ($root -ne $expected) { throw 'Normal installation uses only the current user Programs\Reweave directory.' }
    }
    if ((Test-Path -LiteralPath $root) -and !(Test-Path -LiteralPath $root -PathType Container)) {
        throw 'The installation target is not a directory.'
    }
    if ($Operation -eq 'Install') {
        $payload = Get-AbsolutePath $PayloadRoot
        Assert-PlainPath $payload
        $manifest = Read-Manifest $payload
        $oldFiles = @{}
        $shortcutOwned = $false
        if ((Test-Path -LiteralPath $root -PathType Container) -and @(Get-ChildItem -LiteralPath $root -Force).Count -gt 0) {
            $oldMarker = Assert-Marker $root
            if ($oldMarker.PSObject.Properties.Name -contains 'shortcut_owned') { $shortcutOwned = [bool]$oldMarker.shortcut_owned }
            $oldManifest = Read-Manifest $root
            foreach ($file in $oldManifest.files) {
                $target = Get-OwnedPath $root $file.path
                if ((Test-Path -LiteralPath $target) -and !(Test-MatchingFile $target $file)) {
                    throw 'An installed file was modified. Preserve or move that file before updating.'
                }
                $oldFiles[$file.path] = $file
            }
        }
        $newFiles = @{}
        foreach ($file in $manifest.files) {
            $source = Get-OwnedPath $payload $file.path
            $target = Get-OwnedPath $root $file.path
            if (!(Test-MatchingFile $source $file)) { throw 'A payload file does not match its manifest.' }
            if ((Test-Path -LiteralPath $target) -and !$oldFiles.ContainsKey($file.path)) {
                throw 'An unrelated existing file conflicts with the new installation.'
            }
            $parent = [IO.Directory]::GetParent($target)
            while ($parent -and $parent.FullName -ne $root) {
                if ((Test-Path -LiteralPath $parent.FullName) -and !(Test-Path -LiteralPath $parent.FullName -PathType Container)) {
                    throw 'A parent directory conflicts with an existing file.'
                }
                $parent = $parent.Parent
            }
            $newFiles[$file.path] = $file
        }
        $uninstaller = Join-Path $payload 'Uninstall.exe'
        Assert-PlainPath $uninstaller
        if (!(Test-Path -LiteralPath $uninstaller -PathType Leaf) -or $newFiles.ContainsKey('Uninstall.exe')) {
            throw 'The generated uninstaller is missing or conflicts with the payload.'
        }
        $uninstallTarget = Get-OwnedPath $root 'Uninstall.exe'
        if ((Test-Path -LiteralPath $uninstallTarget) -and !$oldFiles.ContainsKey('Uninstall.exe')) {
            throw 'An unrelated file conflicts with the uninstaller.'
        }
        $uninstallEntry = [pscustomobject]@{path='Uninstall.exe'; sha256=(Get-FileDigest $uninstaller); size=(Get-Item -LiteralPath $uninstaller).Length}
        $manifest.files = @($manifest.files) + @($uninstallEntry)
        $newFiles['Uninstall.exe'] = $uninstallEntry
        if ($Isolated -ne '1' -and (Test-Path -LiteralPath $uninstallKey)) {
            $registration = Get-ItemProperty -LiteralPath $uninstallKey
            if (!($registration.PSObject.Properties.Name -contains 'InstallLocation') -or
                $registration.InstallLocation -ne $root -or
                !($registration.PSObject.Properties.Name -contains 'ReweaveProductId') -or
                $registration.ReweaveProductId -ne $productId) {
                throw 'An unrelated Windows application registration already uses this name.'
            }
        }
        # All payload bytes, existing ownership, destinations and path ancestry
        # have passed validation. No target mutation occurs above this point.
        $null = [IO.Directory]::CreateDirectory($root)
        foreach ($file in $manifest.files) {
            $target = Get-OwnedPath $root $file.path
            $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            [IO.File]::Copy((Get-OwnedPath $payload $file.path), $target, $true)
        }
        foreach ($file in $oldFiles.Values) {
            if (!$newFiles.ContainsKey($file.path)) {
                $target = Get-OwnedPath $root $file.path
                if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
            }
        }
        Write-Json (Join-Path $root $manifestName) $manifest
        $marker = @{schema=1;product=$productId;root=$root;isolated=$Isolated;workspace=$script:workspace;shortcut_owned=$shortcutOwned}
        Write-Json (Join-Path $root $markerName) $marker
        if ($Isolated -ne '1') {
            $null = New-Item -Path $uninstallKey -Force
            $properties = @{DisplayName='Reweave';DisplayVersion=$manifest.version;Publisher='Reweave contributors';InstallLocation=$root;ReweaveProductId=$productId;UninstallString=('"' + (Join-Path $root 'Uninstall.exe') + '"');NoModify=1;NoRepair=1}
            foreach ($name in $properties.Keys) { $null = New-ItemProperty -Path $uninstallKey -Name $name -Value $properties[$name] -Force }
            $startMenu = [Environment]::GetFolderPath('Programs')
            $shortcutPath = Join-Path $startMenu 'Reweave.lnk'
            if (!(Test-Path -LiteralPath $shortcutPath)) {
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut($shortcutPath)
                $shortcut.TargetPath = Join-Path $root 'Reweave.exe'
                $shortcut.WorkingDirectory = $root
                $shortcut.Save()
                $marker.shortcut_owned = $true
                Write-Json (Join-Path $root $markerName) $marker
            }
        }
        Write-Output 'Reweave installed. The application was not started.'
    } else {
        $marker = Assert-Marker $root
        $manifest = Read-Manifest $root
        $retained = 0
        # Read-Manifest resolves every path before the first removal.
        foreach ($file in $manifest.files) {
            $target = Get-OwnedPath $root $file.path
            if (Test-MatchingFile $target $file) {
                Remove-Item -LiteralPath $target -Force
            } elseif (Test-Path -LiteralPath $target) {
                $retained += 1
            }
        }
        Remove-Item -LiteralPath (Join-Path $root $manifestName) -Force
        Remove-Item -LiteralPath (Join-Path $root $markerName) -Force
        Remove-EmptyOwnedDirectories $root $manifest.files
        if (@(Get-ChildItem -LiteralPath $root -Force).Count -eq 0) { Remove-Item -LiteralPath $root -Force }
        if ($Isolated -ne '1') {
            if (Test-Path -LiteralPath $uninstallKey) {
                $registration = Get-ItemProperty -LiteralPath $uninstallKey
                if (($registration.PSObject.Properties.Name -contains 'InstallLocation') -and
                    $registration.InstallLocation -eq $root -and
                    ($registration.PSObject.Properties.Name -contains 'ReweaveProductId') -and
                    $registration.ReweaveProductId -eq $productId) {
                    Remove-Item -LiteralPath $uninstallKey -Force
                }
            }
            $shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Reweave.lnk'
            if (($marker.PSObject.Properties.Name -contains 'shortcut_owned') -and $marker.shortcut_owned -and
                (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut($shortcutPath)
                if ($shortcut.TargetPath -eq (Join-Path $root 'Reweave.exe')) { Remove-Item -LiteralPath $shortcutPath -Force }
            }
        }
        Write-Output "Reweave uninstalled. User data and unrelated files were preserved. Modified installed files retained: $retained."
    }
    exit 0
} catch {
    # Do not emit paths or exception traces into the installer UI.
    Write-Output ('Reweave installation operation stopped: ' + $_.Exception.Message)
    exit 1
}
