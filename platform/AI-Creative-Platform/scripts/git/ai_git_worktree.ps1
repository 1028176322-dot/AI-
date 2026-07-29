[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "Diagnose", "Ensure", "OpenBash", "OpenGui", "Pull", "Push")]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,
    [string]$AgentId = $env:AI_AGENT_ID,
    [string]$WorktreeBase,
    [ValidateSet("Auto", "Slash", "Flat")]
    [string]$BranchMode = "Auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Resolve-Executable {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [IO.Path]::GetFullPath($candidate)
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Required executable was not found: $($Candidates -join ', ')"
}

function Invoke-Git {
    param(
        [string]$WorkingDirectory,
        [string[]]$Arguments,
        [switch]$AllowFailure
    )
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(
            & $script:GitExecutable `
                -c core.longpaths=true `
                -C $WorkingDirectory @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw (
            "git $($Arguments -join ' ') failed ($exitCode):`n" +
            ($output -join "`n"))
    }
    return @{
        exit_code = $exitCode
        text = ($output -join "`n").Trim()
    }
}

function Get-RepositoryId {
    param([string]$Root)
    $normalized = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar).ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($normalized)
        $hash = $sha.ComputeHash($bytes)
        return (
            ([BitConverter]::ToString($hash) -replace "-", "").
                Substring(0, 12))
    } finally {
        $sha.Dispose()
    }
}

function Enter-RepositoryLock {
    param([string]$RepositoryId)
    $lockDirectory = $script:CoordinatorDirectory
    if ([string]::IsNullOrWhiteSpace($lockDirectory)) {
        throw "CoordinatorDirectory is not initialized"
    }
    New-Item -ItemType Directory -Path $lockDirectory -Force | Out-Null
    $lockPath = Join-Path $lockDirectory "$RepositoryId.lock"
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            return [IO.File]::Open(
                $lockPath,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None)
        } catch [IO.IOException] {
            Start-Sleep -Milliseconds 250
        }
    }
    throw (
        "Another AI is registering or synchronizing a worktree. " +
        "Timed out after 30 seconds: $lockPath")
}

function Resolve-AgentId {
    param([string]$Requested)
    if ([string]::IsNullOrWhiteSpace($Requested)) {
        $Requested = Read-Host (
            "AI identifier (letters, digits, dot, underscore, hyphen)")
    }
    $Requested = [string]$Requested
    if ($Requested -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$") {
        throw (
            "AgentId must match " +
            "^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
    }
    if ($Requested -match "^(main|master|release|coordinator)$") {
        throw "Reserved AgentId: $Requested"
    }
    return $Requested.ToLowerInvariant()
}

function Get-AgentBranchCandidates {
    param(
        [string]$Id,
        [string]$Mode
    )
    if ($Mode -eq "Slash") {
        return @("codex/$Id")
    }
    if ($Mode -eq "Flat") {
        return @("codex-$Id")
    }
    return @("codex/$Id", "codex-$Id")
}

function Test-BranchRefCapability {
    param(
        [string]$Root,
        [string]$Branch,
        [string]$Target
    )
    $suffix = [Guid]::NewGuid().ToString("N").Substring(0, 12)
    $probeRef = "refs/heads/$Branch-ref-probe-$suffix"
    $created = $false
    try {
        $create = Invoke-Git $Root @(
            "update-ref", "-m", "ai-worktree-ref-capability-probe",
            $probeRef, $Target, ("0" * 40)
        ) -AllowFailure
        if ($create.exit_code -ne 0) {
            return @{
                ok = $false
                ref = $probeRef
                detail = $create.text
            }
        }
        $created = $true
        $verify = Invoke-Git $Root @(
            "rev-parse", "--verify", $probeRef
        ) -AllowFailure
        if ($verify.exit_code -ne 0 -or $verify.text -ne $Target) {
            return @{
                ok = $false
                ref = $probeRef
                detail = (
                    "git reported success but ref verification failed; " +
                    "actual='$($verify.text)'")
            }
        }
        return @{
            ok = $true
            ref = $probeRef
            detail = "created-and-verified"
        }
    } finally {
        if ($created) {
            Invoke-Git $Root @(
                "update-ref", "-d", $probeRef, $Target
            ) -AllowFailure | Out-Null
        }
    }
}

function Get-RemoteBranchTip {
    param(
        [string]$Root,
        [string]$Branch,
        [switch]$AllowMissing,
        [switch]$FetchObject
    )
    $remoteRef = "refs/heads/$Branch"
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        $query = Invoke-Git $Root @(
            "ls-remote", "--exit-code", "origin", $remoteRef
        ) -AllowFailure
        if ($query.exit_code -eq 2 -and $AllowMissing) {
            return $null
        }
        if ($query.exit_code -ne 0) {
            throw (
                "Unable to resolve authoritative remote ref " +
                "'$remoteRef' (exit=$($query.exit_code)):`n" +
                $query.text)
        }
        $rows = @(
            $query.text -split "\r?\n" |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $match = @(
            $rows | Where-Object {
                $fields = $_ -split "\s+"
                $fields.Count -ge 2 -and $fields[1] -eq $remoteRef
            })
        if ($match.Count -ne 1) {
            throw (
                "Remote ref response is ambiguous for '$remoteRef':`n" +
                $query.text)
        }
        $parts = $match[0] -split "\s+"
        $sha = [string]$parts[0]
        if ($sha -notmatch "^[0-9a-fA-F]{40,64}$") {
            throw "Remote ref returned invalid object id: $sha"
        }
        $sha = $sha.ToLowerInvariant()
        if (-not $FetchObject) {
            return @{
                branch = $Branch
                ref = $remoteRef
                sha = $sha
                source = "git-ls-remote"
            }
        }

        $existingObject = Invoke-Git $Root @(
            "cat-file", "-e", "$sha`^{commit}"
        ) -AllowFailure
        if ($existingObject.exit_code -eq 0) {
            return @{
                branch = $Branch
                ref = $remoteRef
                sha = $sha
                source = "git-ls-remote+existing-object"
            }
        }

        # An explicit remote ref without a destination updates FETCH_HEAD and
        # the object database, but does not depend on refs/remotes/origin/*.
        Invoke-Git $Root @(
            "fetch", "--no-tags", "origin", $remoteRef
        ) | Out-Null
        $objectProbe = Invoke-Git $Root @(
            "cat-file", "-e", "$sha`^{commit}"
        ) -AllowFailure
        if ($objectProbe.exit_code -eq 0) {
            return @{
                branch = $Branch
                ref = $remoteRef
                sha = $sha
                source = "git-ls-remote+explicit-fetch"
            }
        }
    }
    throw (
        "Remote '$remoteRef' changed during fetch or its advertised commit " +
        "was not downloaded after 3 attempts")
}

function Resolve-AgentBranch {
    param(
        [string]$Root,
        [string]$Id,
        [string]$Mode,
        [string]$Target
    )
    $candidates = @(Get-AgentBranchCandidates $Id $Mode)
    foreach ($candidate in $candidates) {
        $local = Invoke-Git $Root @(
            "show-ref", "--verify", "--quiet",
            "refs/heads/$candidate"
        ) -AllowFailure
        if ($local.exit_code -eq 0) {
            return @{
                branch = $candidate
                ref_mode = if ($candidate.Contains("/")) {
                    "slash"
                } else {
                    "flat"
                }
                reason = "existing-local-ref"
                diagnostics = @()
            }
        }
    }

    $diagnostics = @()
    foreach ($candidate in $candidates) {
        $probe = Test-BranchRefCapability $Root $candidate $Target
        $diagnostics += @{
            branch = $candidate
            ok = [bool]$probe.ok
            detail = [string]$probe.detail
        }
        if ($probe.ok) {
            return @{
                branch = $candidate
                ref_mode = if ($candidate.Contains("/")) {
                    "slash"
                } else {
                    "flat"
                }
                reason = "ref-capability-probe-passed"
                diagnostics = $diagnostics
            }
        }
    }
    throw (
        "No branch reference scheme is writable. " +
        "This is a .git write/lock problem, not a packed refs/codex " +
        "namespace conflict. Diagnostics: " +
        ($diagnostics | ConvertTo-Json -Compress -Depth 5))
}

function Get-RepositoryLockReport {
    param([string]$Root)
    $common = (Invoke-Git $Root @(
        "rev-parse", "--git-common-dir")).text
    $commonPath = Resolve-GitReportedPath $Root $common
    $paths = @(
        (Join-Path $commonPath "index.lock"),
        (Join-Path $commonPath "packed-refs.lock"),
        (Join-Path $commonPath "HEAD.lock")
    )
    $rows = @()
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $item = Get-Item -LiteralPath $path
            $rows += @{
                path = $item.FullName
                length = $item.Length
                last_write_utc = $item.LastWriteTimeUtc.ToString("o")
            }
        }
    }
    return $rows
}

function Resolve-GitReportedPath {
    param(
        [string]$WorkingDirectory,
        [string]$ReportedPath
    )
    if ([IO.Path]::IsPathRooted($ReportedPath)) {
        return [IO.Path]::GetFullPath($ReportedPath)
    }
    return [IO.Path]::GetFullPath(
        (Join-Path $WorkingDirectory $ReportedPath))
}

function Assert-AgentWorktree {
    param(
        [string]$Path,
        [string]$ExpectedRoot,
        [string[]]$ExpectedBranches
    )
    $actualRoot = (
        Invoke-Git $Path @("rev-parse", "--show-toplevel")).text
    $actualBranch = (
        Invoke-Git $Path @("branch", "--show-current")).text
    if ([IO.Path]::GetFullPath($actualRoot) -ne
        [IO.Path]::GetFullPath($Path)) {
        throw "Existing path is not the expected worktree: $Path"
    }
    if ($actualBranch -notin $ExpectedBranches) {
        throw (
            "Existing worktree uses branch '$actualBranch', expected one " +
            "of '$($ExpectedBranches -join ', ')': $Path")
    }
    $commonDirectory = (
        Invoke-Git $Path @("rev-parse", "--git-common-dir")).text
    $expectedCommon = (
        Invoke-Git $ExpectedRoot @("rev-parse", "--git-common-dir")).text
    $actualCommonPath = Resolve-GitReportedPath `
        $Path $commonDirectory
    $expectedCommonPath = Resolve-GitReportedPath `
        $ExpectedRoot $expectedCommon
    if ($actualCommonPath -ne $expectedCommonPath) {
        throw "Existing worktree belongs to another repository: $Path"
    }
}

function Ensure-AgentWorktree {
    param(
        [string]$Root,
        [string]$Id,
        [string]$Base,
        [string]$RepositoryId,
        [string]$Mode
    )
    $branchCandidates = @(Get-AgentBranchCandidates $Id $Mode)
    $path = Join-Path $Base $Id
    $lockHandle = Enter-RepositoryLock $RepositoryId
    try {
        if (Test-Path -LiteralPath $path -PathType Container) {
            Assert-AgentWorktree $path $Root $branchCandidates
            $branch = (
                Invoke-Git $path @("branch", "--show-current")).text
            return @{
                path = $path
                branch = $branch
                branch_mode = if ($branch.Contains("/")) {
                    "slash"
                } else {
                    "flat"
                }
                branch_reason = "existing-worktree"
                created = $false
            }
        }

        New-Item -ItemType Directory -Path $Base -Force | Out-Null
        $mainRemote = Get-RemoteBranchTip `
            $Root "main" -FetchObject
        $originMain = [string]$mainRemote.sha
        $resolution = Resolve-AgentBranch `
            $Root $Id $Mode $originMain
        $branch = [string]$resolution.branch
        $branchProbe = Invoke-Git $Root @(
            "show-ref", "--verify", "--quiet", "refs/heads/$branch"
        ) -AllowFailure
        $createdBranch = $false
        $branchTarget = $null
        try {
            if ($branchProbe.exit_code -ne 0) {
                $branchRemote = Get-RemoteBranchTip `
                    $Root $branch -AllowMissing -FetchObject
                $branchTarget = if ($branchRemote) {
                    [string]$branchRemote.sha
                } else {
                    $originMain
                }
                Invoke-Git $Root @(
                    "update-ref", "-m", "ai-worktree-create:$Id",
                    "refs/heads/$branch", $branchTarget, ("0" * 40)
                ) | Out-Null
                $createdBranch = $true
                $verified = (
                    Invoke-Git $Root @(
                        "rev-parse", "--verify",
                        "refs/heads/$branch")).text
                if ($verified -ne $branchTarget) {
                    throw (
                        "Branch ref verification failed after creation: " +
                        "$branch expected=$branchTarget actual=$verified")
                }
            }
            Invoke-Git $Root @(
                "worktree", "add", $path, $branch) | Out-Null
            Invoke-Git $path @(
                "branch", "--unset-upstream", $branch
            ) -AllowFailure | Out-Null
            Assert-AgentWorktree $path $Root @($branch)
        } catch {
            Invoke-Git $Root @(
                "worktree", "remove", "--force", $path
            ) -AllowFailure | Out-Null
            if ($createdBranch -and $branchTarget) {
                Invoke-Git $Root @(
                    "update-ref", "-d",
                    "refs/heads/$branch", $branchTarget
                ) -AllowFailure | Out-Null
            }
            Invoke-Git $Root @(
                "worktree", "prune") -AllowFailure | Out-Null
            $locks = Get-RepositoryLockReport $Root
            throw (
                "$($_.Exception.Message)`n" +
                "Rollback used compare-and-swap for only this invocation's " +
                "branch. Repository index.lock was not deleted because it " +
                "may belong to another AI. Locks: " +
                ($locks | ConvertTo-Json -Compress -Depth 4))
        }
        return @{
            path = $path
            branch = $branch
            branch_mode = [string]$resolution.ref_mode
            branch_reason = [string]$resolution.reason
            branch_diagnostics = $resolution.diagnostics
            created = $true
        }
    } finally {
        $lockHandle.Dispose()
    }
}

$portableRoot = Join-Path $env:USERPROFILE `
    ".workbuddy\vendor\PortableGit"
$GitExecutable = Resolve-Executable @(
    (Join-Path $portableRoot "cmd\git.exe"),
    "git.exe",
    "git"
)
$repoCandidate = [IO.Path]::GetFullPath($RepoPath)
if (-not (Test-Path -LiteralPath $repoCandidate -PathType Container)) {
    throw "Selected directory does not exist: $repoCandidate"
}
$repoProbe = Invoke-Git $repoCandidate @(
    "rev-parse", "--show-toplevel")
$repoRoot = [IO.Path]::GetFullPath($repoProbe.text)
$originProbe = Invoke-Git $repoRoot @(
    "remote", "get-url", "origin")
if ([string]::IsNullOrWhiteSpace($originProbe.text)) {
    throw "Repository has no origin remote: $repoRoot"
}

$resolvedAgentId = Resolve-AgentId $AgentId
$repositoryId = Get-RepositoryId $repoRoot
if ([string]::IsNullOrWhiteSpace($WorktreeBase)) {
    $parent = Split-Path -Parent $repoRoot
    $leaf = Split-Path -Leaf $repoRoot
    $WorktreeBase = Join-Path $parent "$leaf-ai-worktrees"
}
$resolvedBase = [IO.Path]::GetFullPath($WorktreeBase)
if ($resolvedBase -eq $repoRoot -or
    $resolvedBase.StartsWith(
        $repoRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw (
        "WorktreeBase must be outside the coordinator working tree: " +
        $resolvedBase)
}
$CoordinatorDirectory = Join-Path $resolvedBase ".coordination"

if ($Action -eq "Diagnose") {
    $target = (
        Invoke-Git $repoRoot @("rev-parse", "--verify", "HEAD")).text
    $branchResolution = $null
    $resolutionError = $null
    try {
        $branchResolution = Resolve-AgentBranch `
            $repoRoot $resolvedAgentId $BranchMode $target
    } catch {
        $resolutionError = $_.Exception.Message
    }
    $remoteMain = $null
    $remoteMainError = $null
    try {
        $remoteMain = Get-RemoteBranchTip `
            $repoRoot "main"
    } catch {
        $remoteMainError = $_.Exception.Message
    }
    $cachedOriginMain = (
        Invoke-Git $repoRoot @(
            "rev-parse", "--verify",
            "refs/remotes/origin/main"
        ) -AllowFailure).text
    [ordered]@{
        status = if ($branchResolution) { "READY" } else { "BLOCKED" }
        action = $Action
        agent_id = $resolvedAgentId
        coordinator_root = $repoRoot
        git_executable = $GitExecutable
        git_version = (
            Invoke-Git $repoRoot @("--version")).text
        longpaths_effective = (
            Invoke-Git $repoRoot @(
                "config", "--get", "core.longpaths")).text
        ref_storage = (
            Invoke-Git $repoRoot @(
                "config", "--get", "extensions.refStorage"
            ) -AllowFailure).text
        requested_branch_mode = $BranchMode
        selected = $branchResolution
        error = $resolutionError
        remote_main_authoritative = $remoteMain
        origin_main_cached = $cachedOriginMain
        origin_main_cache_matches = (
            $remoteMain -and
            $cachedOriginMain -eq [string]$remoteMain.sha)
        remote_main_error = $remoteMainError
        repository_locks = @(Get-RepositoryLockReport $repoRoot)
        packed_codex_namespace_conflict = $false
        note = (
            "refs/codex/* and refs/heads/codex/* are separate namespaces")
    } | ConvertTo-Json -Depth 6
    exit 0
}

$worktree = Ensure-AgentWorktree `
    $repoRoot $resolvedAgentId $resolvedBase $repositoryId $BranchMode
$worktreePath = [string]$worktree.path
$branchName = [string]$worktree.branch

if ($Action -eq "Pull") {
    $lockHandle = Enter-RepositoryLock $repositoryId
    try {
        $dirty = (Invoke-Git $worktreePath @(
            "status", "--porcelain")).text
        if (-not [string]::IsNullOrWhiteSpace($dirty)) {
            throw (
                "Agent worktree has uncommitted changes; Pull refused:`n" +
                $dirty)
        }
        $remoteBranch = Get-RemoteBranchTip `
            $worktreePath $branchName -AllowMissing -FetchObject
        $source = if ($remoteBranch) {
            [string]$remoteBranch.sha
        } else {
            [string](Get-RemoteBranchTip `
                $worktreePath "main" -FetchObject).sha
        }
        Invoke-Git $worktreePath @(
            "merge", "--ff-only", $source) | Out-Null
    } finally {
        $lockHandle.Dispose()
    }
}

if ($Action -eq "Push") {
    $lockHandle = Enter-RepositoryLock $repositoryId
    try {
        $currentBranch = (
            Invoke-Git $worktreePath @(
                "branch", "--show-current")).text
        if ($currentBranch -ne $branchName) {
            throw (
                "Push refused: current branch '$currentBranch' is not " +
                "the assigned branch '$branchName'")
        }
        $localSha = (
            Invoke-Git $worktreePath @(
                "rev-parse", "--verify", "HEAD")).text
        Invoke-Git $worktreePath @(
            "push", "origin",
            "HEAD:refs/heads/$branchName") | Out-Null
        $remoteAfter = Get-RemoteBranchTip `
            $worktreePath $branchName
        if ([string]$remoteAfter.sha -ne $localSha) {
            throw (
                "Push verification failed: local=$localSha " +
                "remote=$($remoteAfter.sha)")
        }
    } finally {
        $lockHandle.Dispose()
    }
}

if ($Action -eq "OpenBash") {
    $bash = Resolve-Executable @(
        (Join-Path $portableRoot "git-bash.exe"))
    Start-Process -FilePath $bash `
        -ArgumentList @("--cd=$worktreePath")
}

if ($Action -eq "OpenGui") {
    $gui = Resolve-Executable @(
        (Join-Path $portableRoot "cmd\git-gui.exe"))
    Start-Process -FilePath $gui `
        -ArgumentList @("--working-dir", $worktreePath)
}

[ordered]@{
    status = "READY"
    action = $Action
    agent_id = $resolvedAgentId
    coordinator_root = $repoRoot
    worktree = $worktreePath
    branch = $branchName
    branch_mode = [string]$worktree.branch_mode
    branch_reason = [string]$worktree.branch_reason
    created = [bool]$worktree.created
    origin = $originProbe.text
    rule = (
        "Each AI pushes only its assigned branch; " +
        "main is coordinator-only.")
} | ConvertTo-Json -Depth 4
