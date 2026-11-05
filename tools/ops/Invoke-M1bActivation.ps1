# Owner activation for M1b. Preparation only until the Lead merges.
# -PreflightOnly performs no deploy, seed, scrub, or Production write.
# Requires Windows PowerShell 5.1. Reads files with [IO.File], never Get-Content -Raw.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MergedSha,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedPriorHead,
    [string]$ExpectedRegistrySha256 = 'debe116947d13959d611e983311b1e93ac29acf4686d9c66d6e1ed52435e6756',
    [int]$ExpectedT0 = 34,
    [int]$ExpectedLegacy = 3,
    [int]$ExpectedSidecar = 34,
    [string]$ProductionRepo = 'T:\StockLookup\production-v1\stock-core-private',
    [string]$EvidenceRoot = 'T:\StockLookup\production-v1\retained-evidence',
    [string]$Python = 'T:\StockLookup\production-v1\environments\core-313\Scripts\python.exe',
    [int64]$MinFreeBytes = 365072220160,
    [int64]$MinAvailableRamBytes = 4294967296,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$RegistryRelative = 'config/daily_research_session_input_registry.json'

function Get-LfSha256([string]$path) {
    $bytes = [IO.File]::ReadAllBytes($path)
    $normalized = New-Object System.Collections.Generic.List[byte]
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -eq 13 -and ($i + 1) -lt $bytes.Length -and $bytes[$i + 1] -eq 10) { continue }
        $normalized.Add($bytes[$i])
    }
    $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($normalized.ToArray())
    return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
}

function Get-Git([string]$repo, [string[]]$gitArgs) {
    $output = & git -C $repo @gitArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("git failed: " + ($gitArgs -join ' ') + " " + ($output | Out-String)) }
    return (($output | Out-String).Trim())
}

function Get-GitBlobSha256([string]$repo, [string]$spec) {
    $out = Join-Path ([IO.Path]::GetTempPath()) (([guid]::NewGuid().ToString('n')) + '.bin')
    $err = $out + '.err'
    try {
        $proc = Start-Process -FilePath 'git' -ArgumentList @('-C', $repo, 'cat-file', 'blob', $spec) -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            $detail = ''
            if (Test-Path -LiteralPath $err) { $detail = [IO.File]::ReadAllText($err) }
            throw ("git cat-file failed: " + $detail)
        }
        $bytes = [IO.File]::ReadAllBytes($out)
        $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
    }
    finally {
        Remove-Item -LiteralPath $out, $err -Force -ErrorAction SilentlyContinue
    }
}

function Get-Preflight {
    $failures = New-Object System.Collections.Generic.List[string]
    $os = Get-CimInstance Win32_OperatingSystem
    $ram = [int64]$os.FreePhysicalMemory * 1024
    if ($ram -lt $MinAvailableRamBytes) { $failures.Add('RAM_BELOW_FLOOR') }
    $free = [int64]([IO.DriveInfo]::new('T').AvailableFreeSpace)
    if ($free -lt $MinFreeBytes) { $failures.Add('T_FREE_BELOW_FLOOR') }
    $self = $PID
    $writers = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $self -and $_.CommandLine -and (
            $_.CommandLine -match 'run_owner_daily' -or $_.CommandLine -match 'owner_daily'
        )
    })
    if ($writers.Count -gt 0) { $failures.Add('WRITER_PROCESS') }
    $indexLock = Join-Path $ProductionRepo '.git\index.lock'
    if (Test-Path -LiteralPath $indexLock) { $failures.Add('GIT_INDEX_LOCK') }
    $lockRoot = 'T:\StockLookup\production-v1\run-logs'
    $dailyLocks = @(Get-ChildItem -LiteralPath $lockRoot -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
        -not $_.PSIsContainer -and $_.Name -match 'lock'
    })
    if ($dailyLocks.Count -gt 0) { $failures.Add('DAILY_LOCK') }
    $head = Get-Git $ProductionRepo @('rev-parse', 'HEAD')
    if ($head -ne $ExpectedPriorHead) { $failures.Add('PRODUCTION_HEAD_MISMATCH') }
    $branch = Get-Git $ProductionRepo @('rev-parse', '--abbrev-ref', 'HEAD')
    if ($branch -ne 'main') { $failures.Add('PRODUCTION_BRANCH_NOT_MAIN') }
    $committedSha = Get-GitBlobSha256 $ProductionRepo "${head}:${RegistryRelative}"
    if ($committedSha -ne $ExpectedRegistrySha256) { $failures.Add('REGISTRY_COMMIT_MISMATCH') }
    $worktreeRegistry = Join-Path $ProductionRepo $RegistryRelative
    $worktreeSha = Get-LfSha256 $worktreeRegistry
    if ($worktreeSha -ne $committedSha) { $failures.Add('REGISTRY_WORKTREE_DIRTY') }
    [ordered]@{
        ram_available_bytes = $ram
        t_free_bytes = $free
        production_head = $head
        production_branch = $branch
        registry_commit_sha256 = $committedSha
        registry_worktree_sha256 = $worktreeSha
        merged_sha = $MergedSha
        expected_prior_head = $ExpectedPriorHead
        failures = @($failures)
        pass = ($failures.Count -eq 0)
    }
}

$preflight = Get-Preflight
if ($PreflightOnly -or -not $preflight.pass) {
    $preflight | ConvertTo-Json -Compress | Write-Output
    if (-not $preflight.pass) { exit 2 }
    exit 0
}

Get-Git $ProductionRepo @('fetch', 'origin', $MergedSha)
Get-Git $ProductionRepo @('merge', '--ff-only', $MergedSha)
$deployed = Get-Git $ProductionRepo @('rev-parse', 'HEAD')
if ($deployed -ne $MergedSha) { throw 'DEPLOY_HEAD_MISMATCH' }

function Invoke-Feedback([string[]]$arguments) {
    $stdout = & $Python -B @arguments
    return @{ exit = $LASTEXITCODE; stdout = ($stdout | Out-String).Trim() }
}

Push-Location $ProductionRepo
try {
    $seed = Invoke-Feedback @(
        (Join-Path $ProductionRepo 'tools\run_prospective_decision_outcome_feedback.py'),
        '--seed-state-only', '--root', $EvidenceRoot, '--state-root', $EvidenceRoot
    )
    $seedJson = $seed.stdout | ConvertFrom-Json
    $sidecar = 0
    if ($seedJson.metrics -and $null -ne $seedJson.metrics.sidecar_hits) { $sidecar = [int]$seedJson.metrics.sidecar_hits }
    $seedOk = ($seed.exit -eq 33 -and $seedJson.status -eq 'SEEDED' -and [int]$seedJson.t0_count -eq $ExpectedT0 -and [int]$seedJson.legacy_count -eq $ExpectedLegacy -and $sidecar -eq $ExpectedSidecar)
    if (-not $seedOk) {
        [ordered]@{ status = 'SEED_REJECTED'; exit = $seed.exit; stdout = $seed.stdout } | ConvertTo-Json -Compress | Write-Output
        exit 3
    }
    $scrub = Invoke-Feedback @(
        (Join-Path $ProductionRepo 'tools\run_prospective_decision_outcome_feedback.py'),
        '--scrub-sources', '--root', $EvidenceRoot, '--state-root', $EvidenceRoot
    )
    if ($scrub.exit -ne 0) {
        [ordered]@{ status = 'SCRUB_REJECTED'; exit = $scrub.exit; stdout = $scrub.stdout } | ConvertTo-Json -Compress | Write-Output
        exit 4
    }
}
finally {
    Pop-Location
}

$stamp = Get-Date -Format 'yyyyMMdd'
$receiptDir = Join-Path 'T:\StockLookup\production-v1\recovery-checkpoints' ($stamp + '-m1b-activation')
New-Item -ItemType Directory -Force -Path $receiptDir | Out-Null
$receiptPath = Join-Path $receiptDir 'receipt.json'
$receipt = [ordered]@{
    status = 'ACTIVATED'
    merged_sha = $MergedSha
    prior_head = $ExpectedPriorHead
    deployed_head = $deployed
    seed_exit = 33
    seed_status = 'SEEDED'
    t0_count = $ExpectedT0
    legacy_count = $ExpectedLegacy
    sidecar_hits = $ExpectedSidecar
    scrub_exit = 0
    evidence_root = $EvidenceRoot
    state_root = $EvidenceRoot
    preflight = $preflight
}
[IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 6))
Write-Output $receiptPath
exit 0
