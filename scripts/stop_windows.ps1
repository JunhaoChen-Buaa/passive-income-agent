$ErrorActionPreference = "Stop"

$Ports = @(5174, 8010)

Write-Host "== Stopping 被动收益 Agent =="

foreach ($port in $Ports) {
  $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($conn in $connections) {
    $processId = $conn.OwningProcess
    if ($processId) {
      try {
        $proc = Get-Process -Id $processId -ErrorAction Stop
        Write-Host "Stopping port $port PID $processId ($($proc.ProcessName))"
        Stop-Process -Id $processId -Force
      } catch {
        Write-Host "Could not stop PID $processId for port ${port}: $($_.Exception.Message)" -ForegroundColor Yellow
      }
    }
  }
}

Write-Host "Stop command finished." -ForegroundColor Green
