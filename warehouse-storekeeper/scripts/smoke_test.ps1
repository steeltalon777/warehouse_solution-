#requires -Version 5.1
<#
.SYNOPSIS
  Безопасный smoke-тест скилла warehouse-storekeeper.

.DESCRIPTION
  1. Проверяет наличие Python и .venv скилла.
  2. Проверяет конфигурацию и ACL секретов (config check).
  3. health, whoami, capabilities.
  4. Безопасный catalog search (только чтение).
  5. НЕ создаёт draft без флага -SmokeDraft.

.PARAMETER SmokeDraft
  Разрешает создание тестового черновика. ТОЛЬКО на devstand с тестовым
  токеном. Черновик остаётся в статусе draft (submit невозможен для скилла).

.EXAMPLE
  .\smoke_test.ps1
  .\smoke_test.ps1 -SmokeDraft
#>
[CmdletBinding()]
param(
    [switch]$SmokeDraft
)

$ErrorActionPreference = "Continue"
$SkillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiPy    = Join-Path $SkillDir "scripts\warehouse_api.py"
$Passed = 0; $Failed = 0

function Step($name, [scriptblock]$block) {
    Write-Host "`n--- $name ---" -ForegroundColor Cyan
    $ok = & $block
    if ($ok) { $script:Passed++; Write-Host "[PASS] $name" -ForegroundColor Green }
    else     { $script:Failed++; Write-Host "[FAIL] $name" -ForegroundColor Red }
    return $ok
}

function Invoke-Api([string[]]$ApiArgs) {
    $json = & $script:PythonExe $ApiPy @ApiArgs 2>$null
    if (-not $json) { return $null }
    try { return ($json | ConvertFrom-Json) } catch { return $null }
}

# --- 1. Python / venv ---------------------------------------------------------
$PythonExe = $null
Step "Python и окружение скилла" {
    $venvPython = Join-Path $SkillDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { $script:PythonExe = $venvPython }
    else {
        foreach ($c in @("python", "py")) {
            try { & $c --version 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $script:PythonExe = $c; break } } catch { }
        }
    }
    if (-not $script:PythonExe) { Write-Host "Python не найден"; return $false }
    Write-Host "Python: $($script:PythonExe)"
    if (-not (Test-Path $ApiPy)) { Write-Host "Не найден $ApiPy"; return $false }
    & $script:PythonExe -c "import httpx" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "Нет httpx — выполните bootstrap.ps1"; return $false }
    return $true
} | Out-Null

if (-not $PythonExe) { Write-Host "`nSmoke прерван: нет окружения. Итог: PASS=$Passed FAIL=$Failed"; exit 1 }

# --- 2. Конфигурация и ACL ------------------------------------------------------
Step "Конфигурация и ACL секретов" {
    $r = Invoke-Api @("config", "check")
    if (-not $r) { Write-Host "config check не вернул JSON"; return $false }
    $r.data | Format-List | Out-String | Write-Host
    if (-not $r.data.base_url_configured) { Write-Host "Не задан SYNC_SERVER_BASE_URL"; return $false }
    if (-not $r.data.user_token_present) { Write-Host "Не задан SYNC_SERVER_USER_TOKEN"; return $false }
    if (-not $r.data.secrets_acl_safe) { Write-Host "ACL небезопасен — запустите protect_secrets.ps1"; return $false }
    return $true
}

# --- 3. health (с диагностикой curl.exe при сбое) ------------------------------
Step "health" {
    $r = Invoke-Api @("health")
    if ($r -and $r.ok) { Write-Host "status: $($r.data.status)"; return $true }
    Write-Host "health не пройден, диагностика соединения (curl.exe):"
    $envFile = Join-Path $env:LOCALAPPDATA "WarehouseAgent\secrets\syncserver.env"
    $baseUrl = $null
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern "^SYNC_SERVER_BASE_URL=(.+)$" | Select-Object -First 1
        if ($match) { $baseUrl = $match.Matches.Groups[1].Value.Trim() }
    }
    if ($baseUrl) {
        $code = & curl.exe -s -o NUL -w "%{http_code}" --max-time 5 "$baseUrl/api/v1/health"
        Write-Host "curl $baseUrl/api/v1/health -> HTTP $code"
    }
    return $false
}

# --- 4. whoami ------------------------------------------------------------------
Step "whoami" {
    $r = Invoke-Api @("whoami")
    if ($r -and $r.ok) { Write-Host "user: $($r.data.user.username), role: $($r.data.user.role)"; return $true }
    if ($r) { Write-Host "error: $($r.errors[0].code) $($r.errors[0].message)" }
    return $false
}

# --- 5. capabilities -------------------------------------------------------------
Step "capabilities" {
    $r = Invoke-Api @("capabilities")
    if ($r -and $r.ok) {
        Write-Host "role: $($r.data.role); can_create_operations: $($r.data.permissions_summary.can_create_operations)"
        Write-Host "sites: $(($r.data.available_sites | ForEach-Object { $_.name }) -join ', ')"
        return $true
    }
    return $false
}

# --- 6. Безопасный catalog search --------------------------------------------------
Step "catalog search (только чтение)" {
    $r = Invoke-Api @("catalog", "search", "--query", "шайба", "--page-size", "5")
    if ($r -and $r.ok) { Write-Host "найдено: $($r.data.total_count)"; return $true }
    if ($r) { Write-Host "error: $($r.errors[0].code) $($r.errors[0].message)" }
    return $false
}

# --- 7. Опционально: тестовый draft на devstand -------------------------------------
if ($SmokeDraft) {
    Step "SmokeDraft: создание тестового черновика (devstand)" {
        $search = Invoke-Api @("catalog", "search", "--query", "шайба", "--page-size", "1")
        if (-not ($search -and $search.ok -and $search.data.total_count -ge 1)) {
            Write-Host "Нет ни одной позиции каталога для теста"; return $false
        }
        $item = $search.data.items[0]
        $siteId = $null
        $cap = Invoke-Api @("capabilities")
        if ($cap -and $cap.ok -and $cap.data.default_site) { $siteId = $cap.data.default_site.site_id }
        if (-not $siteId) { Write-Host "Нет default_site — укажите SYNC_SERVER_SITE_ID"; return $false }
        $req = @{
            operation_type = "RECEIVE"; site_id = $siteId
            notes = "SMOKE-TEST draft, удалить через Warehouse"
            lines = @(@{ line_number = 1; item_id = $item.id; qty = 1; raw_name = "smoke $($item.name)" })
        }
        $reqFile = Join-Path $env:TEMP "warehouse-smoke-draft.json"
        $req | ConvertTo-Json -Depth 5 | Set-Content $reqFile -Encoding UTF8
        $r = Invoke-Api @("draft", "create", "--input", $reqFile)
        Remove-Item $reqFile -Force -ErrorAction SilentlyContinue
        if ($r -and $r.ok -and $r.data.status -eq "draft") {
            Write-Host "Создан черновик $($r.data.id) (display: $($r.data.display_number)). Он НЕ проведён."
            $v = Invoke-Api @("draft", "validate", "--draft-id", $r.data.id)
            if ($v -and $v.ok) { Write-Host "validate: valid=$($v.data.valid)" }
            return $true
        }
        if ($r) { Write-Host "error: $($r.errors[0].code) $($r.errors[0].message)" }
        return $false
    }
} else {
    Write-Host "`n--- SmokeDraft пропущен (по умолчанию draft не создаётся; флаг -SmokeDraft — только devstand) ---"
}

Write-Host "`n== Итог smoke-теста: PASS=$Passed FAIL=$Failed ==" -ForegroundColor $(if ($Failed) { "Red" } else { "Green" })
exit $(if ($Failed) { 1 } else { 0 })
