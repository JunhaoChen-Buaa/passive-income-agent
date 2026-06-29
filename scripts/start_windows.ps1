$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$LogsDir = Join-Path $ProjectRoot "logs"
$RunFile = Join-Path $LogsDir "local-run.json"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$NpmCache = Join-Path $ProjectRoot ".npm-cache"

function Load-EnvFile {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return }
  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#") -or (-not $line.Contains("="))) { continue }
    $parts = $line.Split("=", 2)
    $name = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if ($name) {
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}

function Get-PortOwner {
  param([int]$Port)
  $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($conn) { return $conn.OwningProcess }
  return $null
}

function Get-NpmCommand {
  $npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
  if ($npmCmd) { return $npmCmd.Source }
  $npm = Get-Command "npm" -ErrorAction SilentlyContinue
  if ($npm) { return $npm.Source }
  throw "npm not found. Please run scripts\install_windows.ps1 after installing Node.js."
}

if (-not (Test-Path $VenvPython)) {
  throw "Backend virtual environment not found. Please run scripts\install_windows.ps1 first."
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
  throw "Frontend dependencies not found. Please run scripts\install_windows.ps1 first."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
Load-EnvFile (Join-Path $ProjectRoot ".env")

$Npm = Get-NpmCommand
$started = @()

Write-Host "== Starting 被动收益 Agent =="

$backendOwner = Get-PortOwner 8010
if ($backendOwner) {
  Write-Host "Backend already listening on 127.0.0.1:8010 (PID $backendOwner)."
} else {
  $backendOut = Join-Path $LogsDir "backend.out.log"
  $backendErr = Join-Path $LogsDir "backend.err.log"
  $backend = Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8010") `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru
  $started += [pscustomobject]@{ name = "backend"; pid = $backend.Id; port = 8010 }
  Write-Host "Backend started (PID $($backend.Id))."
}

$frontendOwner = Get-PortOwner 5174
if ($frontendOwner) {
  Write-Host "Frontend already listening on 127.0.0.1:5174 (PID $frontendOwner)."
} else {
  $frontendOut = Join-Path $LogsDir "frontend.out.log"
  $frontendErr = Join-Path $LogsDir "frontend.err.log"
  $frontendCommand = "`"$Npm`" --cache `"$NpmCache`" run dev -- --host 127.0.0.1 --port 5174"
  $frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", $frontendCommand) `
    -WorkingDirectory $FrontendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru
  $started += [pscustomobject]@{ name = "frontend"; pid = $frontend.Id; port = 5174 }
  Write-Host "Frontend started (PID $($frontend.Id))."
}

$runState = [pscustomobject]@{
  started_at = (Get-Date).ToString("s")
  project_root = $ProjectRoot
  processes = $started
}
$runState | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $RunFile -Encoding UTF8

Start-Sleep -Seconds 3

try {
  $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8010/api/health" -TimeoutSec 5
  Write-Host "Backend health: $($health.StatusCode)"
} catch {
  Write-Host "Backend health check is not ready yet. Check logs\backend.err.log if the page does not load." -ForegroundColor Yellow
}

Write-Host "Opening http://127.0.0.1:5174/ ..."
Start-Process "http://127.0.0.1:5174/"

Write-Host ""
Write-Host "被动收益 Agent is running." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5174/"
Write-Host "Backend:  http://127.0.0.1:8010/api/health"
Write-Host "Stop with: powershell -ExecutionPolicy Bypass -File .\scripts\stop_windows.ps1"
