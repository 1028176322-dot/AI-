[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
throw (
    "REJECTED: the legacy sandbox Broker deployment path is disabled. " +
    "Use `platform broker deploy --mode Plan/Apply/Verify/Rollback` so every " +
    "device uses scripts/logs/deploy_broker_windows.ps1 through the governed " +
    "platform CLI.")
