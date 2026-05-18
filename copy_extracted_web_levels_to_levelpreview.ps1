[CmdletBinding()]
param(
    [string]$SourceRoot = (Join-Path $PSScriptRoot "extracted\web_levels"),
    [string]$OutputRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "SwordOfConvallaria_LevelPreview")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$targetRoot = Join-Path $OutputRoot "web_levels"
$indexPath = Join-Path $SourceRoot "index.json"

function Reset-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Get-ChildItem -LiteralPath $Path -Force | Remove-Item -Recurse -Force
    }
    else {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | Copy-Item -Destination $Destination -Recurse -Force
}

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Missing source folder: $SourceRoot"
}
if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Missing extracted level index: $indexPath"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Reset-Directory -Path $targetRoot
Copy-DirectoryContents -Source $SourceRoot -Destination $targetRoot

$index = Get-Content -LiteralPath (Join-Path $targetRoot "index.json") -Raw | ConvertFrom-Json
Write-Host ("Copied extracted web levels to {0}" -f $targetRoot)
Write-Host ("Copied {0} extracted map entries out of {1} total" -f $index.extractedCount, $index.levelCount)
