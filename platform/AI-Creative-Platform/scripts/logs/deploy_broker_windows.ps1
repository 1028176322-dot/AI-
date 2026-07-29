[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Plan", "Apply", "Verify", "Rollback")]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$PythonExecutable,
    [string]$TaskRunnerAccount,
    [string]$WriterAccount,
    [string]$ServiceName,
    [string]$InitiatingIdentity,
    [int]$Port = 0,
    [switch]$AutoElevate,
    [switch]$RemoveIdentities
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$PlatformRoot = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$BrokerCli = Join-Path $PSScriptRoot "broker_cli.py"
$ServiceHost = Join-Path $PSScriptRoot "broker_windows_service.py"
$ReportPath = Join-Path $ProjectRoot `
    "runtime\learning\broker-deployment.json"
$VerificationPath = Join-Path $ProjectRoot `
    "runtime\learning\broker-verification.json"
$Drafts = Join-Path $ProjectRoot "chapters\drafts"
$Approved = Join-Path $ProjectRoot "chapters\approved"

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Project root not found: $ProjectRoot"
}
if (-not (Test-Path -LiteralPath (
    Join-Path $ProjectRoot "PROJECT_LAYOUT.yaml") -PathType Leaf)) {
    throw "PROJECT_LAYOUT.yaml not found; unmanaged projects cannot deploy Broker"
}
$projectDrive = [IO.Path]::GetPathRoot($ProjectRoot)
if ($projectDrive -notmatch "^[A-Za-z]:\\$") {
    throw (
        "Project root must be on a local Windows drive; UNC/network paths " +
        "are not supported")
}
$driveInfo = [IO.DriveInfo]::new($projectDrive)
if ([string]$driveInfo.DriveFormat -ne "NTFS") {
    throw (
        "Project root must be on NTFS; detected " +
        "$($driveInfo.DriveFormat)")
}

function Get-DeploymentId {
    param([string]$Value)
    $normalized = [IO.Path]::GetFullPath($Value).TrimEnd(
        [IO.Path]::DirectorySeparatorChar).ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($normalized)
        $hash = $sha.ComputeHash($bytes)
        $hex = [BitConverter]::ToString($hash) -replace "-", ""
        return $hex.Substring(0, 8)
    } finally {
        $sha.Dispose()
    }
}

function Resolve-PythonExecutable {
    param([string]$Requested)
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        $candidates += $Requested
    }
    $candidates += (Join-Path $PlatformRoot ".venv\Scripts\python.exe")
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += $command.Source
    }
    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and
            (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    throw (
        "Python runtime not found. Use the canonical CLI " +
        "`platform broker deploy`, or pass -PythonExecutable explicitly.")
}

$PythonExecutable = Resolve-PythonExecutable $PythonExecutable
$PythonHome = Split-Path -Parent $PythonExecutable
$DeploymentId = Get-DeploymentId $ProjectRoot
$ExistingReport = $null
if (Test-Path -LiteralPath $ReportPath -PathType Leaf) {
    try {
        $ExistingReport = Get-Content -LiteralPath $ReportPath -Raw |
            ConvertFrom-Json
    } catch {
        $ExistingReport = $null
    }
}
$ExistingDeployment = if (
    $ExistingReport -and
    [string]$ExistingReport.deployment_id -eq $DeploymentId) {
    $ExistingReport
} else {
    $null
}
$LegacyMigrationObservations = @()
if ([string]::IsNullOrWhiteSpace($TaskRunnerAccount)) {
    $TaskRunnerAccount = if ($ExistingDeployment.taskrunner_account) {
        [string]$ExistingDeployment.taskrunner_account
    } else {
        "ACP_TR_$DeploymentId"
    }
}
if ([string]::IsNullOrWhiteSpace($WriterAccount)) {
    $WriterAccount = if ($ExistingDeployment.writer_account) {
        [string]$ExistingDeployment.writer_account
    } else {
        "ACP_CW_$DeploymentId"
    }
}
if ([string]::IsNullOrWhiteSpace($ServiceName)) {
    $ServiceName = if ($ExistingDeployment.service_name) {
        [string]$ExistingDeployment.service_name
    } else {
        "AIStyleCW_$DeploymentId"
    }
}
if ($Port -eq 0) {
    $Port = if ($ExistingDeployment.port) {
        [int]$ExistingDeployment.port
    } else {
        48000 + (
            [Convert]::ToInt32($DeploymentId.Substring(0, 4), 16) % 8000)
    }
}
if ($Port -lt 1024 -or $Port -gt 65535) {
    throw "Port must be between 1024 and 65535"
}
$RegistrySubPath = "SOFTWARE\AI-Creative-Platform\Brokers\$DeploymentId"
$RegistryProviderPath = "HKLM:\$RegistrySubPath"
$CurrentIdentity = (
    [Security.Principal.WindowsIdentity]::GetCurrent().Name)
if ([string]::IsNullOrWhiteSpace($InitiatingIdentity)) {
    $InitiatingIdentity = $CurrentIdentity
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Require-Administrator {
    if (-not (Test-Administrator)) {
        throw "Administrator privileges are required for $Mode"
    }
}

function Stop-GovernedService {
    param([string]$Name)
    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $service -or $service.Status -eq "Stopped") {
        return
    }
    try {
        Stop-Service -Name $Name -Force -ErrorAction Stop
    } catch {
        # Stop-Service can race with a service that has already stopped.
    }
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if (-not $service -or $service.Status -eq "Stopped") {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Service $Name did not reach STOPPED state"
}

function Invoke-ElevatedSelf {
    function ConvertTo-PowerShellLiteral {
        param([string]$Value)
        return "'" + $Value.Replace("'", "''") + "'"
    }
    $command = (
        "& " + (ConvertTo-PowerShellLiteral $PSCommandPath) +
        " -Mode " + (ConvertTo-PowerShellLiteral $Mode) +
        " -ProjectRoot " + (ConvertTo-PowerShellLiteral $ProjectRoot) +
        " -PythonExecutable " +
            (ConvertTo-PowerShellLiteral $PythonExecutable) +
        " -TaskRunnerAccount " +
            (ConvertTo-PowerShellLiteral $TaskRunnerAccount) +
        " -WriterAccount " +
            (ConvertTo-PowerShellLiteral $WriterAccount) +
        " -ServiceName " + (ConvertTo-PowerShellLiteral $ServiceName) +
        " -InitiatingIdentity " +
            (ConvertTo-PowerShellLiteral $InitiatingIdentity) +
        " -Port " + [string]$Port
    )
    if ($RemoveIdentities) {
        $command += " -RemoveIdentities"
    }
    $command += "; exit `$LASTEXITCODE"
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($command))
    $arguments = (
        "-NoProfile -ExecutionPolicy Bypass -EncodedCommand " + $encoded)
    $child = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden `
        -Wait -PassThru
    exit $child.ExitCode
}

function New-HexSecret {
    param([int]$ByteCount = 32)
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return (
        [BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
}

function New-AccountPassword {
    return "Aa1!$(New-HexSecret -ByteCount 24)"
}

function Find-AvailableLoopbackPort {
    param([int]$StartingPort)
    for ($offset = 0; $offset -lt 128; $offset++) {
        $candidate = $StartingPort + $offset
        if ($candidate -gt 65535) {
            break
        }
        $listener = $null
        try {
            $listener = [Net.Sockets.TcpListener]::new(
                [Net.IPAddress]::Loopback, $candidate)
            $listener.Start()
            return $candidate
        } catch {
            continue
        } finally {
            if ($listener) {
                $listener.Stop()
            }
        }
    }
    throw "No available loopback port found from $StartingPort"
}

function Write-ClientRegistryConfiguration {
    param([string]$ClientToken)
    New-Item -Path $RegistryProviderPath -Force | Out-Null
    New-ItemProperty -Path $RegistryProviderPath -Name "ClientToken" `
        -Value $ClientToken -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryProviderPath -Name "Host" `
        -Value "127.0.0.1" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryProviderPath -Name "Port" `
        -Value $Port -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegistryProviderPath -Name "ProjectRoot" `
        -Value $ProjectRoot -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryProviderPath -Name "ServiceName" `
        -Value $ServiceName -PropertyType String -Force | Out-Null

    $acl = Get-Acl -Path $RegistryProviderPath
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($entry in @(
        @("NT AUTHORITY\SYSTEM", "FullControl"),
        @("BUILTIN\Administrators", "FullControl"),
        @("$env:COMPUTERNAME\$TaskRunnerAccount", "ReadKey"),
        @($InitiatingIdentity, "ReadKey")
    )) {
        $rights = [Enum]::Parse(
            [Security.AccessControl.RegistryRights], $entry[1])
        $rule = [Security.AccessControl.RegistryAccessRule]::new(
            $entry[0],
            $rights,
            [Security.AccessControl.InheritanceFlags]::None,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    Set-Acl -Path $RegistryProviderPath -AclObject $acl
}

function Test-ExplicitAclEntryPresent {
    param(
        [string]$Path,
        [string]$Account,
        [ValidateSet("Allow", "Deny")]
        [string]$AccessType
    )
    $acl = Get-Acl -LiteralPath $Path
    foreach ($rule in $acl.Access) {
        if ($rule.IsInherited) {
            continue
        }
        $identity = [string]$rule.IdentityReference
        $matchesAccount = (
            $identity.Equals(
                $Account, [StringComparison]::OrdinalIgnoreCase) -or
            $identity.EndsWith(
                "\$Account", [StringComparison]::OrdinalIgnoreCase))
        if ($matchesAccount -and
            [string]$rule.AccessControlType -ieq $AccessType) {
            return $true
        }
    }
    return $false
}

function Remove-LegacyAclEntry {
    param(
        [string]$Path,
        [string]$Account,
        [ValidateSet("Allow", "Deny")]
        [string]$AccessType
    )
    $removeOption = if ($AccessType -eq "Deny") {
        "/remove:d"
    } else {
        "/remove:g"
    }
    & icacls.exe $Path $removeOption $Account | Out-Null
    # icacls returns non-zero when the account or ACE is already absent.
    # Read-back is authoritative: only a surviving explicit ACE is failure.
    if (Test-ExplicitAclEntryPresent `
            -Path $Path -Account $Account -AccessType $AccessType) {
        throw (
            "Legacy $AccessType ACL remains after removal: " +
            "$Account on $Path")
    }
}

function Test-ServiceImagePathBoundToProject {
    param(
        [string]$ImagePath,
        [string]$ExpectedProjectRoot
    )
    if ([string]::IsNullOrWhiteSpace($ImagePath)) {
        return $false
    }
    $normalizedRoot = [IO.Path]::GetFullPath(
        $ExpectedProjectRoot).TrimEnd("\")
    $normalizedImagePath = $ImagePath.Replace("/", "\")
    $escapedRoot = [Regex]::Escape($normalizedRoot)
    $projectRootArgumentPattern = (
        '(?:^|\s)--project-root\s+(?:"{0}"|{0})(?=\s|$)' -f
        $escapedRoot)
    return [Regex]::IsMatch(
        $normalizedImagePath,
        $projectRootArgumentPattern,
        [Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

function Get-LegacyServiceAssessment {
    param([string]$Name)
    $servicePath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    if (-not (Test-Path -Path $servicePath)) {
        return [ordered]@{
            service_name = $Name
            registry_present = $false
            service_api_present = $false
            bound_to_current_project = $false
            disposition = "absent"
        }
    }
    $imagePath = [string](
        Get-ItemProperty -Path $servicePath).ImagePath
    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    $boundToCurrentProject = Test-ServiceImagePathBoundToProject `
        -ImagePath $imagePath -ExpectedProjectRoot $ProjectRoot
    return [ordered]@{
        service_name = $Name
        registry_present = $true
        service_api_present = ($null -ne $service)
        bound_to_current_project = $boundToCurrentProject
        image_path = $imagePath
        disposition = if ($boundToCurrentProject) {
            "migrate_current_project"
        } else {
            "skip_foreign_or_unverifiable"
        }
    }
}

function Remove-LegacyDeploymentForCurrentProject {
    $legacyDeployments = @()
    if ($ExistingReport -and -not $ExistingDeployment) {
        $legacyReportedRoot = [string]$ExistingReport.project_root
        $legacyRoot = $null
        if (-not [string]::IsNullOrWhiteSpace($legacyReportedRoot)) {
            try {
                $legacyRoot = [IO.Path]::GetFullPath($legacyReportedRoot)
            } catch {
                $script:LegacyMigrationObservations += [ordered]@{
                    source = "deployment_report"
                    disposition = "skipped_unverifiable_report"
                    reported_project_root = $legacyReportedRoot
                    reason = "project_root is not a valid absolute path"
                }
            }
        } else {
            $script:LegacyMigrationObservations += [ordered]@{
                source = "deployment_report"
                disposition = "skipped_unverifiable_report"
                reason = "project_root is missing"
            }
        }
        $reportBelongsToCurrentProject = (
            -not [string]::IsNullOrWhiteSpace($legacyRoot) -and
            [StringComparer]::OrdinalIgnoreCase.Equals(
                $legacyRoot.TrimEnd("\"), $ProjectRoot.TrimEnd("\")))
        if ($reportBelongsToCurrentProject) {
            $legacyDeployments += @{
                service = [string]$ExistingReport.service_name
                runner = [string]$ExistingReport.taskrunner_account
                writer = [string]$ExistingReport.writer_account
                source = "deployment_report"
            }
        } elseif ($legacyRoot) {
            $script:LegacyMigrationObservations += [ordered]@{
                source = "deployment_report"
                service_name = [string]$ExistingReport.service_name
                disposition = "skipped_foreign_project_report"
                reported_project_root = $legacyRoot
                current_project_root = $ProjectRoot
            }
        }
    }
    if ($ServiceName -ne "AIStyleChapterWriter") {
        $legacyDeployments += @{
            service = "AIStyleChapterWriter"
            runner = "SVC_TaskRunner"
            writer = "SVC_ChapterWriter"
            source = "fixed_legacy_service"
        }
    }

    $legacyRunners = @()
    $legacyWriters = @()
    foreach ($legacy in $legacyDeployments) {
        $legacyService = [string]$legacy.service
        $legacyRunner = [string]$legacy.runner
        $legacyWriter = [string]$legacy.writer
        if (-not [string]::IsNullOrWhiteSpace($legacyRunner)) {
            $legacyRunners += $legacyRunner
        }
        if (-not [string]::IsNullOrWhiteSpace($legacyWriter)) {
            $legacyWriters += $legacyWriter
        }
        if ([string]::IsNullOrWhiteSpace($legacyService) -or
            $legacyService -eq $ServiceName) {
            continue
        }
        $legacyServicePath = (
            "HKLM:\SYSTEM\CurrentControlSet\Services\$legacyService")
        if (Test-Path -Path $legacyServicePath) {
            $assessment = Get-LegacyServiceAssessment -Name $legacyService
            if (-not $assessment.bound_to_current_project) {
                $script:LegacyMigrationObservations += [ordered]@{
                    source = [string]$legacy.source
                    service_name = $legacyService
                    disposition = "skipped_foreign_service"
                    image_path = [string]$assessment.image_path
                    service_api_present = (
                        $assessment.service_api_present -eq $true)
                }
                continue
            }
            Stop-GovernedService -Name $legacyService
            & sc.exe delete $legacyService | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to delete governed legacy service $legacyService"
            }
            Start-Sleep -Seconds 1
            $script:LegacyMigrationObservations += [ordered]@{
                source = [string]$legacy.source
                service_name = $legacyService
                disposition = "deleted_current_project_legacy"
                image_path = [string]$assessment.image_path
            }
        }
    }
    foreach ($path in @($Drafts, $Approved)) {
        foreach ($legacyRunner in ($legacyRunners | Select-Object -Unique)) {
            Remove-LegacyAclEntry `
                -Path $path -Account $legacyRunner -AccessType "Deny"
        }
        foreach ($legacyWriter in ($legacyWriters | Select-Object -Unique)) {
            Remove-LegacyAclEntry `
                -Path $path -Account $legacyWriter -AccessType "Allow"
        }
    }
}

if (
    $Mode -in @("Apply", "Rollback") -and
    -not ("BrokerLsaRights" -as [type])
) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;

public static class BrokerLsaRights {
    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_UNICODE_STRING {
        public UInt16 Length;
        public UInt16 MaximumLength;
        public IntPtr Buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_OBJECT_ATTRIBUTES {
        public UInt32 Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public UInt32 Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    [DllImport("advapi32.dll", PreserveSig = true)]
    private static extern UInt32 LsaOpenPolicy(
        IntPtr systemName,
        ref LSA_OBJECT_ATTRIBUTES objectAttributes,
        UInt32 desiredAccess,
        out IntPtr policyHandle);

    [DllImport("advapi32.dll", PreserveSig = true)]
    private static extern UInt32 LsaAddAccountRights(
        IntPtr policyHandle,
        IntPtr accountSid,
        LSA_UNICODE_STRING[] userRights,
        UInt32 countOfRights);

    [DllImport("advapi32.dll", PreserveSig = true)]
    private static extern UInt32 LsaRemoveAccountRights(
        IntPtr policyHandle,
        IntPtr accountSid,
        bool allRights,
        LSA_UNICODE_STRING[] userRights,
        UInt32 countOfRights);

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaNtStatusToWinError(UInt32 status);

    [DllImport("advapi32.dll")]
    private static extern UInt32 LsaClose(IntPtr policyHandle);

    private const UInt32 POLICY_CREATE_ACCOUNT = 0x00000010;
    private const UInt32 POLICY_LOOKUP_NAMES = 0x00000800;

    private static void ChangeRight(
        string account, string right, bool remove) {
        SecurityIdentifier sid = (SecurityIdentifier)
            new NTAccount(account).Translate(typeof(SecurityIdentifier));
        byte[] sidBytes = new byte[sid.BinaryLength];
        sid.GetBinaryForm(sidBytes, 0);
        IntPtr sidPointer = Marshal.AllocHGlobal(sidBytes.Length);
        IntPtr rightPointer = Marshal.StringToHGlobalUni(right);
        IntPtr policy = IntPtr.Zero;
        try {
            Marshal.Copy(sidBytes, 0, sidPointer, sidBytes.Length);
            LSA_OBJECT_ATTRIBUTES attributes =
                new LSA_OBJECT_ATTRIBUTES();
            attributes.Length =
                (UInt32)Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));
            UInt32 status = LsaOpenPolicy(
                IntPtr.Zero, ref attributes,
                POLICY_CREATE_ACCOUNT | POLICY_LOOKUP_NAMES,
                out policy);
            if (status != 0) {
                throw new Win32Exception(
                    (int)LsaNtStatusToWinError(status));
            }
            LSA_UNICODE_STRING value = new LSA_UNICODE_STRING();
            value.Buffer = rightPointer;
            value.Length = (UInt16)(right.Length * 2);
            value.MaximumLength = (UInt16)((right.Length + 1) * 2);
            LSA_UNICODE_STRING[] rights = { value };
            status = remove
                ? LsaRemoveAccountRights(
                    policy, sidPointer, false, rights, 1)
                : LsaAddAccountRights(
                    policy, sidPointer, rights, 1);
            if (status != 0) {
                throw new Win32Exception(
                    (int)LsaNtStatusToWinError(status));
            }
        } finally {
            if (policy != IntPtr.Zero) {
                LsaClose(policy);
            }
            Marshal.FreeHGlobal(rightPointer);
            Marshal.FreeHGlobal(sidPointer);
        }
    }

    public static void GrantLogOnAsService(string account) {
        ChangeRight(account, "SeServiceLogonRight", false);
    }

    public static void RevokeLogOnAsService(string account) {
        ChangeRight(account, "SeServiceLogonRight", true);
    }
}
"@
}

function Grant-ServiceLogonRight {
    param([string]$Account)
    [BrokerLsaRights]::GrantLogOnAsService(
        "$env:COMPUTERNAME\$Account")
}

function Revoke-ServiceLogonRight {
    param([string]$Account)
    [BrokerLsaRights]::RevokeLogOnAsService(
        "$env:COMPUTERNAME\$Account")
}

function Write-DeploymentReport {
    param([hashtable]$Body)
    $directory = Split-Path -Parent $ReportPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $Body.schema = "style-broker-deployment@1.0.0"
    $Body.deployment_id = $DeploymentId
    $Body.project_root = $ProjectRoot
    $Body.service_name = $ServiceName
    $Body.port = $Port
    $Body.taskrunner_account = $TaskRunnerAccount
    $Body.writer_account = $WriterAccount
    $Body.installed_by = $InitiatingIdentity
    $Body.client_registry_path = $RegistrySubPath
    $Body.generated_at = [DateTimeOffset]::Now.ToString("o")
    $temporary = "$ReportPath.tmp"
    $Body | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $ReportPath -Force
}

function Write-VerificationReport {
    param([hashtable]$Body)
    $directory = Split-Path -Parent $VerificationPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $Body.schema = "style-broker-verification@1.0.0"
    $Body.deployment_id = $DeploymentId
    $Body.project_root = $ProjectRoot
    $Body.service_name = $ServiceName
    $Body.port = $Port
    $Body.taskrunner_account = $TaskRunnerAccount
    $Body.writer_account = $WriterAccount
    $Body.client_registry_path = $RegistrySubPath
    $Body.generated_at = [DateTimeOffset]::Now.ToString("o")
    $temporary = "$VerificationPath.tmp"
    $Body | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary `
        -Destination $VerificationPath -Force
}

function Get-AclVerification {
    $raw = & $PythonExecutable $BrokerCli acl-verify `
        --project-root $ProjectRoot `
        --taskrunner $TaskRunnerAccount `
        --writer $WriterAccount 2>&1
    $exit = $LASTEXITCODE
    return @{
        exit_code = $exit
        output = ($raw -join "`n")
        verified = ($exit -eq 0)
    }
}

function Get-ServiceVerification {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    $raw = & $PythonExecutable $BrokerCli status `
        --project-root $ProjectRoot 2>&1
    $exit = $LASTEXITCODE
    return @{
        exists = ($null -ne $service)
        windows_status = if ($service) {
            [string]$service.Status
        } else {
            "NOT_FOUND"
        }
        broker_reachable = ($exit -eq 0)
        broker_status = ($raw -join "`n")
    }
}

function Get-ClientRegistryVerification {
    if (-not (Test-Path -Path $RegistryProviderPath)) {
        return @{
            verified = $false
            reason = "client registry key is missing"
        }
    }
    $values = Get-ItemProperty -Path $RegistryProviderPath
    $acl = Get-Acl -Path $RegistryProviderPath
    $runner = "$env:COMPUTERNAME\$TaskRunnerAccount"
    $runnerCanRead = $false
    $initiatorCanRead = $false
    foreach ($rule in $acl.Access) {
        if ([string]$rule.IdentityReference -ieq $runner -and
            $rule.AccessControlType -eq "Allow" -and
            ([string]$rule.RegistryRights).Contains("ReadKey")) {
            $runnerCanRead = $true
        }
        if ([string]$rule.IdentityReference -ieq $InitiatingIdentity -and
            $rule.AccessControlType -eq "Allow" -and
            ([string]$rule.RegistryRights).Contains("ReadKey")) {
            $initiatorCanRead = $true
        }
    }
    $verified = (
        -not [string]::IsNullOrWhiteSpace([string]$values.ClientToken) -and
        [string]$values.Host -eq "127.0.0.1" -and
        [int]$values.Port -eq $Port -and
        [IO.Path]::GetFullPath([string]$values.ProjectRoot) -eq $ProjectRoot -and
        [string]$values.ServiceName -eq $ServiceName -and
        $runnerCanRead -and
        $initiatorCanRead)
    return @{
        verified = $verified
        registry_path = $RegistrySubPath
        runner_read = $runnerCanRead
        initiating_identity = $InitiatingIdentity
        initiating_identity_read = $initiatorCanRead
        token_present = (
            -not [string]::IsNullOrWhiteSpace([string]$values.ClientToken))
    }
}

if ($Mode -eq "Plan") {
    $plan = & $PythonExecutable $BrokerCli acl-plan `
        --project-root $ProjectRoot `
        --taskrunner $TaskRunnerAccount `
        --writer $WriterAccount
    $legacyFixedService = Get-LegacyServiceAssessment `
        -Name "AIStyleChapterWriter"
    [ordered]@{
        mode = "Plan"
        project_root = $ProjectRoot
        service_name = $ServiceName
        service_identity = ".\$WriterAccount"
        taskrunner_identity = ".\$TaskRunnerAccount"
        service_host = $ServiceHost
        deployment_id = $DeploymentId
        port = $Port
        secrets = (
            "Apply generates device-local random secrets automatically; " +
            "the Broker key stays in the Windows service environment and " +
            "the client token is stored in an ACL-protected HKLM key.")
        client_registry_path = $RegistrySubPath
        legacy_migration_policy = (
            "Only legacy services whose --project-root exactly matches " +
            "this project are migrated. Foreign or unverifiable legacy " +
            "services and copied deployment reports are recorded and skipped.")
        legacy_fixed_service = $legacyFixedService
        acl_plan = ($plan -join "`n")
        rollback = @(
            "Stop and delete service $ServiceName",
            "Remove explicit ACL entries for both service identities",
            "Delete HKLM:\$RegistrySubPath",
            "Optionally remove the two local identities"
        )
    } | ConvertTo-Json -Depth 8
    exit 0
}

if ($Mode -in @("Apply", "Rollback")) {
    if (-not (Test-Administrator) -and $AutoElevate) {
        Invoke-ElevatedSelf
    }
    Require-Administrator
}

if ($Mode -eq "Apply") {
    $env:STYLE_BROKER_KEY = New-HexSecret -ByteCount 32
    $env:STYLE_BROKER_CLIENT_TOKEN = New-HexSecret -ByteCount 32
    $runnerPlainPassword = New-AccountPassword
    $writerPlainPassword = New-AccountPassword
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        throw "Python executable not found: $PythonExecutable"
    }
    & $PythonExecutable $ServiceHost --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw (
            "Selected Python cannot load the Broker service runtime; " +
            "deployment stopped before changing identities or ACLs")
    }
    New-Item -ItemType Directory -Force -Path $Drafts, $Approved |
        Out-Null
    Remove-LegacyDeploymentForCurrentProject
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    $existingServicePath = (
        "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName")
    $existingServiceRegistryPresent = Test-Path -Path $existingServicePath
    if ($existingServiceRegistryPresent) {
        $existingAssessment = Get-LegacyServiceAssessment -Name $ServiceName
        if (-not $existingAssessment.bound_to_current_project) {
            throw (
                "Derived service name is already bound to another project; " +
                "use an explicitly approved non-conflicting service name")
        }
    }

    $runnerPassword = ConvertTo-SecureString `
        $runnerPlainPassword -AsPlainText -Force
    $writerPassword = ConvertTo-SecureString `
        $writerPlainPassword -AsPlainText -Force
    $runnerUser = Get-LocalUser -Name $TaskRunnerAccount `
        -ErrorAction SilentlyContinue
    if (-not $runnerUser) {
        New-LocalUser -Name $TaskRunnerAccount `
            -Password $runnerPassword `
            -Description (
                "AI platform TaskRunner deployment $DeploymentId") `
            -PasswordNeverExpires | Out-Null
    } else {
        if (-not ([string]$runnerUser.Description).Contains($DeploymentId)) {
            throw (
                "TaskRunner account name is already owned by another " +
                "deployment")
        }
        Set-LocalUser -Name $TaskRunnerAccount `
            -Password $runnerPassword -PasswordNeverExpires $true
    }
    $writerUser = Get-LocalUser -Name $WriterAccount `
        -ErrorAction SilentlyContinue
    if (-not $writerUser) {
        New-LocalUser -Name $WriterAccount `
            -Password $writerPassword `
            -Description (
                "AI platform ChapterWriter deployment $DeploymentId") `
            -PasswordNeverExpires | Out-Null
    } else {
        if (-not ([string]$writerUser.Description).Contains($DeploymentId)) {
            throw (
                "ChapterWriter account name is already owned by another " +
                "deployment")
        }
        Set-LocalUser -Name $WriterAccount `
            -Password $writerPassword -PasswordNeverExpires $true
    }
    & icacls.exe $PythonHome /grant:r `
        "${WriterAccount}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Writer service identity cannot read the Python runtime"
    }
    & icacls.exe $PlatformRoot /grant:r `
        "${WriterAccount}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Writer service identity cannot read the platform runtime"
    }
    Grant-ServiceLogonRight -Account $WriterAccount

    if ($existingServiceRegistryPresent) {
        Stop-GovernedService -Name $ServiceName
        & sc.exe delete $ServiceName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw (
                "Failed to replace the current project's existing Broker " +
                "service $ServiceName")
        }
        Start-Sleep -Seconds 1
    }
    $Port = Find-AvailableLoopbackPort -StartingPort $Port
    Write-ClientRegistryConfiguration `
        -ClientToken $env:STYLE_BROKER_CLIENT_TOKEN
    $binPath = (
        ('"{0}" "{1}" --service-name "{2}" ' +
         '--project-root "{3}" --host 127.0.0.1 --port {4} ' +
         '--deployment-id "{5}" --client-registry-path "{6}"') -f
        $PythonExecutable, $ServiceHost, $ServiceName, $ProjectRoot, $Port,
        $DeploymentId, $RegistrySubPath)
    $writerCredential = [PSCredential]::new(
        ".\$WriterAccount", $writerPassword)
    try {
        New-Service -Name $ServiceName `
            -BinaryPathName $binPath `
            -StartupType Automatic `
            -Credential $writerCredential `
            -Description (
                "AI Creative Platform strict-v2 ChapterWriter Broker") |
            Out-Null
    } catch {
        throw "Windows service creation failed: $($_.Exception.Message)"
    }
    $runnerPlainPassword = $null
    $writerPlainPassword = $null
    & sc.exe failure $ServiceName `
        "reset= 86400" "actions= restart/5000/restart/15000/none/0" |
        Out-Null

    $serviceRegistryPath = (
        "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName")
    New-ItemProperty -Path $serviceRegistryPath -Name "Environment" `
        -PropertyType MultiString -Value @(
            "STYLE_BROKER_KEY=$($env:STYLE_BROKER_KEY)",
            "STYLE_BROKER_CLIENT_TOKEN=$($env:STYLE_BROKER_CLIENT_TOKEN)"
        ) -Force | Out-Null

    & $PythonExecutable $BrokerCli acl-apply `
        --project-root $ProjectRoot `
        --taskrunner $TaskRunnerAccount `
        --writer $WriterAccount `
        --confirm-real-change | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ACL application/read-back failed"
    }

    Start-Service -Name $ServiceName
    $reachable = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        & $PythonExecutable $BrokerCli status `
            --project-root $ProjectRoot | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $reachable = $true
            break
        }
    }
    if (-not $reachable) {
        throw "Broker service did not become reachable"
    }

    $probe = Join-Path $Drafts ".taskrunner-write-probe.tmp"
    $deleteProbe = Join-Path $Drafts ".taskrunner-delete-probe.tmp"
    if (Test-Path -LiteralPath $probe) {
        Remove-Item -LiteralPath $probe -Force
    }
    Set-Content -LiteralPath $deleteProbe -Value "must-remain" -Encoding UTF8
    $credential = [PSCredential]::new(
        ".\$TaskRunnerAccount", $runnerPassword)
    $probeCommand = 'echo forbidden>"{0}"' -f $probe
    $process = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/d", "/c", $probeCommand) `
        -Credential $credential -WindowStyle Hidden `
        -Wait -PassThru
    $directWriteDenied = (
        -not (Test-Path -LiteralPath $probe))
    $deleteCommand = 'del /f /q "{0}"' -f $deleteProbe
    $deleteProcess = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/d", "/c", $deleteCommand) `
        -Credential $credential -WindowStyle Hidden `
        -Wait -PassThru
    $directDeleteDenied = (
        (Test-Path -LiteralPath $deleteProbe))
    Remove-Item -LiteralPath $deleteProbe -Force
    if (-not ($directWriteDenied -and $directDeleteDenied)) {
        if (Test-Path -LiteralPath $probe) {
            Remove-Item -LiteralPath $probe -Force
        }
        throw "TaskRunner direct write/delete denial probe failed"
    }

    $acl = Get-AclVerification
    $service = Get-ServiceVerification
    $clientRegistry = Get-ClientRegistryVerification
    $verified = (
        $acl.verified -and
        $service.exists -and
        $service.windows_status -eq "Running" -and
        $service.broker_reachable -and
        $clientRegistry.verified -and
        $directWriteDenied -and
        $directDeleteDenied)
    Write-DeploymentReport @{
        mode = "Apply"
        deployment_state = if ($verified) {
            "DEPLOYED_VERIFIED"
        } else {
            "DEPLOYMENT_FAILED"
        }
        acl = $acl
        service = $service
        client_registry = $clientRegistry
        legacy_migration = @{
            policy = "current-project-only; foreign legacy entries are skipped"
            observations = @($LegacyMigrationObservations)
        }
        taskrunner_direct_write_denied = $directWriteDenied
        taskrunner_direct_delete_denied = $directDeleteDenied
        taskrunner_write_probe_exit_code = $process.ExitCode
        taskrunner_delete_probe_exit_code = $deleteProcess.ExitCode
        secrets_persisted_in_project = $false
        secrets_generated_on_device = $true
        broker_key_location = (
            "Windows Service environment (SCM/registry ACL protected)")
        client_token_location = "HKLM:\$RegistrySubPath"
        rollback_command = (
            "platform broker deploy --mode Rollback " +
            "--project-root `"$ProjectRoot`" --auto-elevate")
    }
    if (-not $verified) {
        throw "Deployment verification did not pass"
    }
    Get-Content -LiteralPath $ReportPath -Raw
    exit 0
}

if ($Mode -eq "Verify") {
    $acl = Get-AclVerification
    $service = Get-ServiceVerification
    $clientRegistry = Get-ClientRegistryVerification
    $priorWriteDenied = (
        $ExistingDeployment -and
        $ExistingDeployment.taskrunner_direct_write_denied -eq $true)
    $priorDeleteDenied = (
        $ExistingDeployment -and
        $ExistingDeployment.taskrunner_direct_delete_denied -eq $true)
    $verified = (
        $acl.verified -and
        $service.exists -and
        $service.windows_status -eq "Running" -and
        $service.broker_reachable -and
        $clientRegistry.verified -and
        $priorWriteDenied -and
        $priorDeleteDenied)
    $verificationBody = @{
        mode = "Verify"
        deployment_state = if ($verified) {
            "DEPLOYED_VERIFIED"
        } else {
            "BLOCKED_NOT_DEPLOYED"
        }
        acl = $acl
        service = $service
        client_registry = $clientRegistry
        taskrunner_direct_write_denied = $priorWriteDenied
        taskrunner_direct_delete_denied = $priorDeleteDenied
        note = (
            "Verify preserves the latest Apply identity probes; " +
            "run Apply when either proof is absent.")
    }
    if ($ExistingDeployment) {
        foreach ($name in @(
            "secrets_persisted_in_project",
            "secrets_generated_on_device",
            "broker_key_location",
            "client_token_location",
            "rollback_command",
            "taskrunner_write_probe_exit_code",
            "taskrunner_delete_probe_exit_code",
            "legacy_migration"
        )) {
            $property = $ExistingDeployment.PSObject.Properties[$name]
            if ($property) {
                $verificationBody[$name] = $property.Value
            }
        }
        $verificationBody["apply_report_generated_at"] = (
            $ExistingDeployment.generated_at)
    }
    Write-VerificationReport $verificationBody
    if (-not $verified) {
        Get-Content -LiteralPath $VerificationPath -Raw
        exit 1
    }
    Write-DeploymentReport $verificationBody
    Get-Content -LiteralPath $ReportPath -Raw
    exit 0
}

if ($Mode -eq "Rollback") {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($service) {
        if ($service.Status -ne "Stopped") {
            Stop-Service -Name $ServiceName -Force
        }
        & sc.exe delete $ServiceName | Out-Null
    }
    foreach ($path in @($Drafts, $Approved)) {
        & icacls.exe $path /remove:d $TaskRunnerAccount | Out-Null
        & icacls.exe $path /remove:g $WriterAccount | Out-Null
    }
    & icacls.exe $PythonHome /remove:g $WriterAccount | Out-Null
    & icacls.exe $PlatformRoot /remove:g $WriterAccount | Out-Null
    if (Test-Path -Path $RegistryProviderPath) {
        Remove-Item -Path $RegistryProviderPath -Recurse -Force
    }
    Revoke-ServiceLogonRight -Account $WriterAccount
    if ($RemoveIdentities) {
        foreach ($name in @($TaskRunnerAccount, $WriterAccount)) {
            if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) {
                Remove-LocalUser -Name $name
            }
        }
    }
    Write-DeploymentReport @{
        mode = "Rollback"
        deployment_state = "ROLLED_BACK"
        client_registry_removed = (
            -not (Test-Path -Path $RegistryProviderPath))
        identities_removed = [bool]$RemoveIdentities
    }
    Get-Content -LiteralPath $ReportPath -Raw
}
