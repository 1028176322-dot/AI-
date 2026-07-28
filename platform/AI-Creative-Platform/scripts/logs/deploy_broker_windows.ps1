[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Plan", "Apply", "Verify", "Rollback")]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExecutable,
    [string]$TaskRunnerAccount = "SVC_TaskRunner",
    [string]$WriterAccount = "SVC_ChapterWriter",
    [string]$ServiceName = "AIStyleChapterWriter",
    [int]$Port = 48731,
    [switch]$RemoveIdentities
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$PlatformRoot = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\.."))
$BrokerCli = Join-Path $PSScriptRoot "broker_cli.py"
$ServiceHost = Join-Path $PSScriptRoot "broker_windows_service.py"
$PythonHome = Split-Path -Parent $PythonExecutable
$ReportPath = Join-Path $ProjectRoot `
    "runtime\learning\broker-deployment.json"
$Drafts = Join-Path $ProjectRoot "chapters\drafts"
$Approved = Join-Path $ProjectRoot "chapters\approved"

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

if (-not ("BrokerLsaRights" -as [type])) {
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
    $Body.project_root = $ProjectRoot
    $Body.service_name = $ServiceName
    $Body.taskrunner_account = $TaskRunnerAccount
    $Body.writer_account = $WriterAccount
    $Body.generated_at = [DateTimeOffset]::Now.ToString("o")
    $temporary = "$ReportPath.tmp"
    $Body | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $ReportPath -Force
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

if ($Mode -eq "Plan") {
    $plan = & $PythonExecutable $BrokerCli acl-plan `
        --project-root $ProjectRoot `
        --taskrunner $TaskRunnerAccount `
        --writer $WriterAccount
    [ordered]@{
        mode = "Plan"
        project_root = $ProjectRoot
        service_name = $ServiceName
        service_identity = ".\$WriterAccount"
        taskrunner_identity = ".\$TaskRunnerAccount"
        service_host = $ServiceHost
        port = $Port
        required_secret_environment = @(
            "STYLE_BROKER_KEY",
            "STYLE_BROKER_CLIENT_TOKEN",
            "STYLE_TASKRUNNER_PASSWORD",
            "STYLE_WRITER_SERVICE_PASSWORD"
        )
        acl_plan = ($plan -join "`n")
        rollback = @(
            "Stop and delete service $ServiceName",
            "Remove explicit ACL entries for both service identities",
            "Optionally remove the two local identities"
        )
    } | ConvertTo-Json -Depth 8
    exit 0
}

Require-Administrator

if ($Mode -eq "Apply") {
    foreach ($name in @(
        "STYLE_BROKER_KEY",
        "STYLE_BROKER_CLIENT_TOKEN",
        "STYLE_TASKRUNNER_PASSWORD",
        "STYLE_WRITER_SERVICE_PASSWORD"
    )) {
        if ([string]::IsNullOrWhiteSpace(
            [Environment]::GetEnvironmentVariable($name))) {
            throw "Required secret environment variable is missing: $name"
        }
    }
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        throw "Python executable not found: $PythonExecutable"
    }
    New-Item -ItemType Directory -Force -Path $Drafts, $Approved |
        Out-Null

    $runnerPassword = ConvertTo-SecureString `
        $env:STYLE_TASKRUNNER_PASSWORD -AsPlainText -Force
    $writerPassword = ConvertTo-SecureString `
        $env:STYLE_WRITER_SERVICE_PASSWORD -AsPlainText -Force
    $runnerUser = Get-LocalUser -Name $TaskRunnerAccount `
        -ErrorAction SilentlyContinue
    if (-not $runnerUser) {
        New-LocalUser -Name $TaskRunnerAccount `
            -Password $runnerPassword `
            -Description "AI platform low-privilege task runner" `
            -PasswordNeverExpires | Out-Null
    } else {
        Set-LocalUser -Name $TaskRunnerAccount `
            -Password $runnerPassword -PasswordNeverExpires $true
    }
    $writerUser = Get-LocalUser -Name $WriterAccount `
        -ErrorAction SilentlyContinue
    if (-not $writerUser) {
        New-LocalUser -Name $WriterAccount `
            -Password $writerPassword `
            -Description "AI platform ChapterWriter Broker" `
            -PasswordNeverExpires | Out-Null
    } else {
        Set-LocalUser -Name $WriterAccount `
            -Password $writerPassword -PasswordNeverExpires $true
    }
    & icacls.exe $PythonHome /grant:r `
        "${WriterAccount}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Writer service identity cannot read the Python runtime"
    }
    Grant-ServiceLogonRight -Account $WriterAccount

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        if ($existing.Status -ne "Stopped") {
            Stop-Service -Name $ServiceName -Force
        }
        & sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
    }
    $binPath = (
        ('"{0}" "{1}" --service-name "{2}" ' +
         '--project-root "{3}" --host 127.0.0.1 --port {4}') -f
        $PythonExecutable, $ServiceHost, $ServiceName, $ProjectRoot, $Port)
    $createOutput = & sc.exe create $ServiceName `
        binPath= $binPath `
        start= auto `
        obj= ".\$WriterAccount" `
        password= $env:STYLE_WRITER_SERVICE_PASSWORD 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("Windows service creation failed: " +
            ($createOutput -join "`n"))
    }
    & sc.exe description $ServiceName `
        "AI Creative Platform strict-v2 ChapterWriter Broker" | Out-Null
    & sc.exe failure $ServiceName `
        "reset= 86400" "actions= restart/5000/restart/15000/none/0" |
        Out-Null

    $serviceKey = "HKLM\SYSTEM\CurrentControlSet\Services\$ServiceName"
    $environmentValue = "STYLE_BROKER_KEY=$($env:STYLE_BROKER_KEY)\0" +
        "STYLE_BROKER_CLIENT_TOKEN=$($env:STYLE_BROKER_CLIENT_TOKEN)"
    & reg.exe add $serviceKey /v Environment /t REG_MULTI_SZ `
        /d $environmentValue /f | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Service environment injection failed"
    }

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
    $verified = (
        $acl.verified -and
        $service.exists -and
        $service.windows_status -eq "Running" -and
        $service.broker_reachable -and
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
        taskrunner_direct_write_denied = $directWriteDenied
        taskrunner_direct_delete_denied = $directDeleteDenied
        taskrunner_write_probe_exit_code = $process.ExitCode
        taskrunner_delete_probe_exit_code = $deleteProcess.ExitCode
        secrets_persisted_in_project = $false
        rollback_command = (
            "powershell -File `"$PSCommandPath`" -Mode Rollback " +
            "-ProjectRoot `"$ProjectRoot`" " +
            "-PythonExecutable `"$PythonExecutable`"")
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
    $verified = (
        $acl.verified -and
        $service.exists -and
        $service.windows_status -eq "Running" -and
        $service.broker_reachable)
    Write-DeploymentReport @{
        mode = "Verify"
        deployment_state = if ($verified) {
            "DEPLOYED_VERIFIED"
        } else {
            "BLOCKED_NOT_DEPLOYED"
        }
        acl = $acl
        service = $service
        taskrunner_direct_write_denied = $null
        note = "Run Apply to execute the direct-write identity probe."
    }
    Get-Content -LiteralPath $ReportPath -Raw
    if (-not $verified) {
        exit 1
    }
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
        identities_removed = [bool]$RemoveIdentities
    }
    Get-Content -LiteralPath $ReportPath -Raw
}
