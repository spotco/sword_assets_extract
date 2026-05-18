[CmdletBinding()]
param(
    [string]$OutputRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "SwordOfConvallaria_LevelPreview"),
    [string]$RemoteAssetBase = "https://raw.githubusercontent.com/spotco/SwordOfConvallaria_LevelPreview/main/web_levels"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$stagingRoot = Join-Path $repoRoot "temp\SwordOfConvallaria_LevelPreview_build"
$stagingSiteRoot = Join-Path $stagingRoot "site"
$viewerRoot = Join-Path $repoRoot "web_level_viewer"
$remoteIndexUrl = "$($RemoteAssetBase.TrimEnd('/'))/index.json"

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

function Copy-GeneratedSite {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )

    New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null
    Reset-Directory -Path (Join-Path $DestinationRoot "vendor")
    Copy-DirectoryContents -Source (Join-Path $SourceRoot "vendor") -Destination (Join-Path $DestinationRoot "vendor")
    Reset-Directory -Path (Join-Path $DestinationRoot "static_assets")
    Copy-DirectoryContents -Source (Join-Path $SourceRoot "static_assets") -Destination (Join-Path $DestinationRoot "static_assets")
    Copy-Item -LiteralPath (Join-Path $SourceRoot "index.html") -Destination (Join-Path $DestinationRoot "index.html") -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot "app.js") -Destination (Join-Path $DestinationRoot "app.js") -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot "styles.css") -Destination (Join-Path $DestinationRoot "styles.css") -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot ".nojekyll") -Destination (Join-Path $DestinationRoot ".nojekyll") -Force
}

function Test-RemoteIndex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -Method Get
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
            return $true
        }
    }
    catch {
        Write-Warning ("Remote asset index is not reachable yet: {0}" -f $Url)
        Write-Warning "The packaged viewer will build, but it will not load maps until that remote web_levels tree exists."
    }
    return $false
}

function Get-ViewerHtml {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TemplatePath,
        [Parameter(Mandatory = $true)]
        [string]$LevelRoot,
        [string]$ApiRoot,
        [Parameter(Mandatory = $true)]
        [bool]$StaticSite
    )

    $apiRootAttr = if ($ApiRoot) { " data-api-root=""$ApiRoot""" } else { "" }
    return (Get-Content -LiteralPath $TemplatePath -Raw).
        Replace("__LEVEL_ROOT__", $LevelRoot.TrimEnd("/")).
        Replace("__API_ROOT_ATTR__", $apiRootAttr).
        Replace("__STATIC_SITE__", $StaticSite.ToString().ToLowerInvariant())
}

Push-Location $repoRoot
try {
    Reset-Directory -Path $stagingRoot
    New-Item -ItemType Directory -Force -Path $stagingSiteRoot | Out-Null

    Write-Host ("Using remote asset base: {0}" -f $RemoteAssetBase)
    [void](Test-RemoteIndex -Url $remoteIndexUrl)

    $templatePath = Join-Path $viewerRoot "index.template.html"
    $indexHtml = Get-ViewerHtml -TemplatePath $templatePath -LevelRoot $RemoteAssetBase -StaticSite $true
    Set-Content -LiteralPath (Join-Path $stagingSiteRoot "index.html") -Value $indexHtml -Encoding UTF8

    Copy-Item -LiteralPath (Join-Path $viewerRoot "app.js") -Destination (Join-Path $stagingSiteRoot "app.js") -Force
    Copy-Item -LiteralPath (Join-Path $viewerRoot "styles.css") -Destination (Join-Path $stagingSiteRoot "styles.css") -Force
    Copy-DirectoryContents -Source (Join-Path $viewerRoot "vendor") -Destination (Join-Path $stagingSiteRoot "vendor")
    Copy-DirectoryContents -Source (Join-Path $viewerRoot "static_assets") -Destination (Join-Path $stagingSiteRoot "static_assets")
    New-Item -ItemType File -Path (Join-Path $stagingSiteRoot ".nojekyll") -Force | Out-Null

    Copy-GeneratedSite -SourceRoot $stagingSiteRoot -DestinationRoot $OutputRoot

    Write-Host ("Packaged static viewer to {0}" -f $OutputRoot)
    Write-Host ("Viewer will fetch assets from {0}" -f $RemoteAssetBase.TrimEnd("/"))
}
finally {
    Pop-Location
}
