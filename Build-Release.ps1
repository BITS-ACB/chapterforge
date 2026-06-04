#Requires -Version 7
<#
.SYNOPSIS
    Builds ChapterForge and packages it into a Windows installer.

.DESCRIPTION
    Runs the full release pipeline:
      1. Tests       — pytest (skippable with -SkipTests)
      2. Docs        — python tools/build_docs.py (skippable with -SkipDocs)
      3. Executables — pyinstaller ChapterForge.spec -> dist\ChapterForge\
      4. Installer   — ISCC.exe installer\ChapterForge.iss -> installer_output\

.PARAMETER SkipTests
    Skip pytest. Useful when iterating on packaging without code changes.

.PARAMETER SkipDocs
    Skip rebuilding the HTML help pages. Use when docs haven't changed.

.PARAMETER SkipInstaller
    Stop after PyInstaller — do not run Inno Setup. Handy for quick smoke tests.

.PARAMETER Open
    Open the installer_output folder in Explorer when the build completes.

.EXAMPLE
    .\Build-Release.ps1
    Full build — tests, docs, PyInstaller, Inno Setup.

.EXAMPLE
    .\Build-Release.ps1 -SkipTests -SkipDocs -Open
    Rebuild executables and installer, open the output folder when done.

.EXAMPLE
    .\Build-Release.ps1 -SkipInstaller
    Build and smoke-test the executables only; skip the installer step.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipDocs,
    [switch]$SkipInstaller,
    [switch]$Open
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

function Write-Step([string]$text) {
    Write-Host "`n$text" -ForegroundColor Cyan
}

function Write-OK([string]$text) {
    Write-Host "  $text" -ForegroundColor Green
}

function Write-Info([string]$text) {
    Write-Host "  $text" -ForegroundColor DarkGray
}

function Invoke-Step([string]$description, [scriptblock]$block) {
    Write-Step $description
    & $block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$description failed (exit $LASTEXITCODE)."
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Resolve project root (the folder containing this script)
# ─────────────────────────────────────────────────────────────────────────────

$root = $PSScriptRoot
Push-Location $root

try {

# ─────────────────────────────────────────────────────────────────────────────
# Detect version from chapterforge/__init__.py
# ─────────────────────────────────────────────────────────────────────────────

$initFile = Join-Path $root 'chapterforge\__init__.py'
$versionLine = Select-String -Path $initFile -Pattern '__version__\s*=\s*"(.+)"'
if (-not $versionLine) {
    throw "Could not read __version__ from $initFile"
}
$version = $versionLine.Matches[0].Groups[1].Value

Write-Host ''
Write-Host ('─' * 60) -ForegroundColor DarkCyan
Write-Host "  ChapterForge $version  —  Release Build" -ForegroundColor White
Write-Host ('─' * 60) -ForegroundColor DarkCyan
$buildStart = [datetime]::Now

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Tests
# ─────────────────────────────────────────────────────────────────────────────

if ($SkipTests) {
    Write-Info '[1/4] Tests skipped (-SkipTests).'
} else {
    Invoke-Step '[1/4] Running tests (pytest)…' {
        python -m pytest -q
    }
    Write-OK 'All tests passed.'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — HTML documentation
# ─────────────────────────────────────────────────────────────────────────────

if ($SkipDocs) {
    Write-Info '[2/4] Docs skipped (-SkipDocs).'
} else {
    Invoke-Step '[2/4] Building HTML documentation…' {
        python tools/build_docs.py
    }
    Write-OK 'Documentation built.'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — PyInstaller
# ─────────────────────────────────────────────────────────────────────────────

Invoke-Step '[3/4] Building executables (PyInstaller)…' {
    # Clean previous output so stale files do not pollute the bundle.
    $distDir = Join-Path $root 'dist\ChapterForge'
    if (Test-Path $distDir) {
        Write-Info "Removing previous dist\ChapterForge\…"
        Remove-Item -Recurse -Force $distDir
    }
    pyinstaller ChapterForge.spec
}
Write-OK "PyInstaller build complete: dist\ChapterForge\"

# Smoke-test the CLI executable
$cliExe = Join-Path $root 'dist\ChapterForge\chapterforge-cli.exe'
if (Test-Path $cliExe) {
    Write-Info 'Smoke testing CLI executable…'
    $smokeOutput = & $cliExe --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "CLI smoke test passed: $smokeOutput"
    } else {
        Write-Host "  WARNING: CLI smoke test returned exit $LASTEXITCODE." -ForegroundColor Yellow
        Write-Host "  Output: $smokeOutput" -ForegroundColor Yellow
    }
} else {
    Write-Host "  WARNING: CLI executable not found at expected path." -ForegroundColor Yellow
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Inno Setup
# ─────────────────────────────────────────────────────────────────────────────

if ($SkipInstaller) {
    Write-Info '[4/4] Installer skipped (-SkipInstaller).'
} else {
    # Locate ISCC.exe across common installation paths.
    $candidatePaths = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        'C:\Program Files\Inno Setup 6\ISCC.exe',
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    )
    $iscc = $candidatePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    # Fall back to PATH lookup
    if (-not $iscc) {
        $onPath = Get-Command ISCC -ErrorAction SilentlyContinue
        if ($onPath) { $iscc = $onPath.Source }
    }

    if (-not $iscc) {
        throw (
            "ISCC.exe not found.`n" +
            "Install Inno Setup 6 from https://jrsoftware.org/isinfo.php`n" +
            "or add its folder to your PATH and re-run."
        )
    }

    Invoke-Step '[4/4] Building installer (Inno Setup)…' {
        Write-Info "ISCC: $iscc"
        & $iscc (Join-Path $root 'installer\ChapterForge.iss')
    }

    $installer = Join-Path $root 'installer_output\ChapterForge-Setup.exe'
    if (Test-Path $installer) {
        $sizeMB = [math]::Round((Get-Item $installer).Length / 1MB, 1)
        Write-OK "Installer: $((Get-Item $installer).FullName)  ($sizeMB MB)"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────

$elapsed = [math]::Round(([datetime]::Now - $buildStart).TotalSeconds, 1)
Write-Host ''
Write-Host ('─' * 60) -ForegroundColor DarkCyan
Write-Host "  Build complete in ${elapsed}s" -ForegroundColor White
Write-Host ('─' * 60) -ForegroundColor DarkCyan
Write-Host ''

if ($Open -and (Test-Path (Join-Path $root 'installer_output'))) {
    Start-Process explorer.exe -ArgumentList (Resolve-Path 'installer_output')
}

} catch {
    Write-Host ''
    Write-Host "BUILD FAILED: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
