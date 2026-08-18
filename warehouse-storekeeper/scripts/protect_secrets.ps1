#requires -Version 5.1
<#
.SYNOPSIS
  Выставляет безопасный ACL на файл секретов syncserver.env.

.DESCRIPTION
  Снимает наследование и оставляет доступ только:
    - текущему Windows-пользователю (Full Control);
    - NT AUTHORITY\SYSTEM (Full Control).
  warehouse_api.py отказывается работать, если ACL шире.

.EXAMPLE
  .\protect_secrets.ps1
  .\protect_secrets.ps1 -Path "D:\secrets\syncserver.env"
#>
[CmdletBinding()]
param(
    [string]$Path = (Join-Path $env:LOCALAPPDATA "WarehouseAgent\secrets\syncserver.env")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Path)) {
    Write-Error "Файл не найден: $Path (сначала создайте его из templates\syncserver.env.example)"
    exit 1
}

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "Файл: $Path"
Write-Host "Текущий пользователь: $CurrentUser"

# Сброс наследования и всех ACE, затем выдача прав только user + SYSTEM.
& icacls $Path /inheritance:r | Out-Null
& icacls $Path /grant:r "${CurrentUser}:(F)" | Out-Null
& icacls $Path /grant:r "NT AUTHORITY\SYSTEM:(F)" | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Error "icacls завершился с ошибкой (код $LASTEXITCODE)"
    exit 1
}

Write-Host "[OK] ACL выставлен. Результат:"
& icacls $Path
