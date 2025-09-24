param(
    [string]$BaseUrl = "http://127.0.0.1:4567",
    [string]$MdUser = $env:MD_USER,
    [string]$MdPass = $env:MD_PASS,
    [string]$StatusMap = "",
    [string]$PreferredLangs = "en,en-us",
    [string]$MissingReport = ".\reports\md_missing_reads.csv",
    [string]$FollowsJson = ".\reports\mangadex_follows.json",
    [string]$LogDir = ".\reports",
    [string]$TitleFilter = "",
    [string]$MigrationSources = "bato.to,mangabuddy,weeb central,mangapark",
    [string]$ExcludeSources = "comick,hitomi",
    [int]$MaxRPM = 240,
    [int]$ReadDelaySec = 2,
    [switch]$Quick,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

function New-Timestamp { (Get-Date -Format "yyyyMMdd_HHmmss") }
function New-EnsurePath { if(-not (Test-Path $args[0])) { New-Item -ItemType Directory -Force -Path $args[0] | Out-Null } }

function Get-Python {
    $py = ".\.venv\Scripts\python.exe"
    if(-not (Test-Path $py)) {
        throw ".\.venv\Scripts\python.exe not found. Create/activate the venv first."
    }
    return $py
}

function Invoke-TestStep {
    param(
        [string]$Name,
        [string[]]$CmdArgs
    )
    New-EnsurePath $LogDir
    $py = Get-Python
    $ts = New-Timestamp
    $log = Join-Path $LogDir (${Name} + "_" + $ts + ".log")
    Write-Host "==> $Name" -ForegroundColor Cyan
    Write-Host "    Log: $log"
    & $py .\import_mangadex_bookmarks_to_suwayomi.py @CmdArgs 2>&1 | Tee-Object -FilePath $log
    if($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        throw "Step failed: $Name"
    }
    Write-Host "[OK] $Name" -ForegroundColor Green
}

# --- Pre-flight ---
New-EnsurePath $LogDir
if([string]::IsNullOrWhiteSpace($MdUser)) {
    if($NonInteractive) { throw "Missing -MdUser and env:MD_USER in NonInteractive mode." }
    $MdUser = Read-Host "Enter MangaDex Username"
}
if([string]::IsNullOrWhiteSpace($MdPass)) {
    if($NonInteractive) { throw "Missing -MdPass and env:MD_PASS in NonInteractive mode." }
    $sec = Read-Host "Enter MangaDex Password" -AsSecureString
    $MdPass = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}

# Build common auth args
$mdAuth = @('--from-follows','--md-username', $MdUser, '--md-password', $MdPass)

# 1) Follows fetch (baseline)
Invoke-TestStep -Name "01_follows_fetch" -CmdArgs @('--base-url', $BaseUrl) + $mdAuth + @('--follows-json', $FollowsJson, '--dry-run', '--no-progress')

# 2) Reading Status Mapping (optional if StatusMap provided)
if(-not [string]::IsNullOrWhiteSpace($StatusMap)) {
    Invoke-TestStep -Name "02_status_mapping" -CmdArgs @('--base-url', $BaseUrl) + $mdAuth + @('--import-reading-status','--status-category-map', $StatusMap, '--print-status-summary', '--dry-run')
}

# 3) Read Chapters (UUID on MangaDex source)
if(-not $Quick) {
    Invoke-TestStep -Name "03_read_uuid" -CmdArgs @('--base-url', $BaseUrl) + $mdAuth + @('--import-read-chapters','--read-sync-delay', "$ReadDelaySec", '--max-read-requests-per-minute', "$MaxRPM")
}

# 4) Read Chapters across sources (number fallback)
Invoke-TestStep -Name "04_read_across_sources" -CmdArgs @('--base-url', $BaseUrl) + $mdAuth + @(
    '--import-read-chapters',
    '--read-sync-number-fallback',
    '--read-sync-across-sources',
    '--read-sync-only-if-ahead',
    '--read-sync-delay', "$ReadDelaySec",
    '--max-read-requests-per-minute', "$MaxRPM",
    '--missing-report', $MissingReport
)

# 5) List Categories
Invoke-TestStep -Name "05_list_categories" -CmdArgs @('--base-url', $BaseUrl, '--list-categories')

# 6) Migration (dry-run, safe defaults) unless Quick
if(-not $Quick) {
    $migArgs = @('--base-url', $BaseUrl, '--migrate-library', '--migrate-threshold-chapters', '1', '--migrate-sources', $MigrationSources, '--exclude-sources', $ExcludeSources, '--migrate-title-threshold','0.6','--best-source','--best-source-candidates','4','--migrate-timeout','20','--dry-run')
    if(-not [string]::IsNullOrWhiteSpace($TitleFilter)) { $migArgs += @('--migrate-filter-title', $TitleFilter) }
    Invoke-TestStep -Name "06_migration_dryrun" -CmdArgs $migArgs
}

# 7) Prune: zero/low-chapter duplicates (dry run)
if(-not $Quick) {
    Invoke-TestStep -Name "07_prune_dups_dryrun" -CmdArgs @('--base-url', $BaseUrl, '--prune-zero-duplicates', '--prune-threshold-chapters', '1', '--dry-run')
}

# 8) Prune: non-preferred languages (dry run)
if(-not $Quick) {
    Invoke-TestStep -Name "08_prune_lang_dryrun" -CmdArgs @('--base-url', $BaseUrl, '--prune-nonpreferred-langs', '--preferred-langs', $PreferredLangs, '--prune-lang-threshold','1','--dry-run')
}

Write-Host "All selected tests completed successfully." -ForegroundColor Green
