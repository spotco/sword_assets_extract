[CmdletBinding()]
param(
    [string]$OutRoot = (Join-Path $PSScriptRoot "extracted\web_levels"),
    [int]$MapLimit = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$indexPath = Join-Path $OutRoot "index.json"

function Invoke-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python was not found on PATH."
}

Push-Location $repoRoot
try {
    Write-Host "Refreshing level index..."
    Invoke-RepoPython -Arguments @(".\level_probe\export_level_index.py", "--out-root", $OutRoot)

    if (-not (Test-Path -LiteralPath $indexPath)) {
        throw "Missing level index after refresh: $indexPath"
    }

    $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
    $levels = @($index.levels)
    if ($MapLimit -gt 0) {
        $levels = @($levels | Select-Object -First $MapLimit)
    }
    if ($levels.Count -eq 0) {
        throw "No levels found in $indexPath"
    }

    $failures = [System.Collections.Generic.List[string]]::new()
    $processed = 0

    foreach ($level in $levels) {
        $processed += 1
        $mapName = [string]$level.mapName
        $bundle = [string]$level.bundle

        Write-Host ("[{0}/{1}] Extracting {2}" -f $processed, $levels.Count, $mapName)

        try {
            Invoke-RepoPython -Arguments @(".\level_probe\extract_battle_grid.py", "--bundle", $bundle)
            Invoke-RepoPython -Arguments @(".\level_probe\dump_scene_layout.py", "--bundle", $bundle)
            Invoke-RepoPython -Arguments @(".\level_probe\export_grid_json.py", "--map", $mapName, "--out-root", $OutRoot)
            Invoke-RepoPython -Arguments @(".\level_probe\export_mesh_json.py", "--map", $mapName, "--bundle", $bundle, "--out-root", $OutRoot)
        }
        catch {
            $failures.Add(("{0} :: {1}" -f $mapName, $_.Exception.Message))
            Write-Warning ("Failed {0}: {1}" -f $mapName, $_.Exception.Message)
        }
    }

    Write-Host "Refreshing level index after extraction..."
    Invoke-RepoPython -Arguments @(".\level_probe\export_level_index.py", "--out-root", $OutRoot)
    $finalIndex = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json

    Write-Host ("Processed {0} map(s); extracted count is now {1} of {2}" -f $levels.Count, $finalIndex.extractedCount, $finalIndex.levelCount)

    if ($failures.Count -gt 0) {
        Write-Warning ("{0} map(s) failed during extraction:" -f $failures.Count)
        foreach ($failure in $failures) {
            Write-Warning $failure
        }
        throw "Completed with extraction failures."
    }
}
finally {
    Pop-Location
}
