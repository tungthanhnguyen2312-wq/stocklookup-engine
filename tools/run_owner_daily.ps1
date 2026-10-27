[CmdletBinding()]
param(
    [string]$ReplayCompletedSession,
    [string]$EntryScript,
    [string]$LogDirectory,
    [switch]$NoPause,
    [switch]$Diagnostic
)
$ErrorActionPreference = 'Stop'
# Resolve the persistent writer before any log/directory is created. A stale
# shell cannot independently revive the old C checkout after a qualified cutover.
$activeBinding = Join-Path $env:USERPROFILE '.stocklookup/active_workspace.json'
if (Test-Path -LiteralPath $activeBinding) {
    $binding = Get-Content -LiteralPath $activeBinding -Raw | ConvertFrom-Json
    if ($binding.schema -ne 'stocklookup_active_workspace/v1') { throw 'Active workspace binding schema invalid' }
    $activeProfile = [string]$binding.profile_path
    $activeBytes = [IO.File]::ReadAllBytes($activeProfile)
    $activeHasher = [Security.Cryptography.SHA256]::Create()
    try { $activeHash = [BitConverter]::ToString($activeHasher.ComputeHash($activeBytes)).Replace('-', '').ToLowerInvariant() }
    finally { $activeHasher.Dispose() }
    if (-not [IO.Path]::IsPathRooted($activeProfile) -or
        $activeHash -ne $binding.profile_sha256) {
        throw 'Active workspace profile identity invalid'
    }
    $activeRoles = ([Text.Encoding]::UTF8.GetString($activeBytes) | ConvertFrom-Json).roles
    if ([IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)) -ne [IO.Path]::GetFullPath($activeRoles.producer)) {
        throw 'Checkout is not the active production writer'
    }
    if ($env:STOCK_LOOKUP_WORKSPACE_PROFILE -and
        [IO.Path]::GetFullPath($env:STOCK_LOOKUP_WORKSPACE_PROFILE) -ne [IO.Path]::GetFullPath($activeProfile)) {
        throw 'Stale workspace profile environment'
    }
    $activePython = [string]$binding.python_path
    if (-not [IO.Path]::IsPathRooted($activePython) -or -not (Test-Path -LiteralPath $activePython -PathType Leaf)) {
        throw 'Active Python unavailable'
    }
    if ($env:STOCK_LOOKUP_PYTHON -and [IO.Path]::GetFullPath($env:STOCK_LOOKUP_PYTHON) -ne [IO.Path]::GetFullPath($activePython)) {
        throw 'Stale Python environment'
    }
    $env:STOCK_LOOKUP_WORKSPACE_PROFILE = $activeProfile
    $env:STOCK_LOOKUP_PYTHON = $activePython
}
# Presentation, logs and the sequential relaunch live in the stdlib Python host, so
# this PowerShell front door (stocklookup.ps1 daily, legacy Desktop CMD) only forwards.
# The zero-PowerShell one-click route is tools/run_owner_daily.cmd.
$python = 'C:\Program Files\Python313\python.exe'
if ($env:STOCK_LOOKUP_PYTHON) {
    if (-not (Test-Path -LiteralPath $env:STOCK_LOOKUP_PYTHON -PathType Leaf)) { throw 'Configured Python unavailable' }
    $python = $env:STOCK_LOOKUP_PYTHON
}
if (-not (Test-Path $python)) { $python = 'python' }
$hostArguments = @('-I', '-X', 'utf8', '-B', (Join-Path $PSScriptRoot 'owner_daily_host.py'))
if ($ReplayCompletedSession) { $hostArguments += @('--replay-completed-session', $ReplayCompletedSession) }
if ($EntryScript) { $hostArguments += @('--entry-script', $EntryScript) }
if ($LogDirectory) { $hostArguments += @('--log-directory', $LogDirectory) }
if ($NoPause) { $hostArguments += '--no-pause' }
if ($Diagnostic) { $hostArguments += '--diagnostic' }
& $python @hostArguments
exit $LASTEXITCODE
