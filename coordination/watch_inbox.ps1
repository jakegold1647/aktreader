# Coordination-bus watcher for the BUILDER (Sol) session.
# Blocks until a new message lands in coordination\inbox_sol\ or STATUS_BOARD.md changes,
# then exits 0 with a report line. Exits 2 on timeout (default 10 min) — just run it again.
# Usage:  powershell -File coordination\watch_inbox.ps1 [-TimeoutMinutes 10]
param([int]$TimeoutMinutes = 10)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$inbox = Join-Path $root 'inbox_sol'
$board = Join-Path $root 'STATUS_BOARD.md'
# Report the current inbox contents BEFORE watching. A message that arrived while you were
# working is invisible to the watch loop (it is in the baseline snapshot) — this is the fix for
# the 29 Jul msg-036 miss. Always read anything newer than your last ACK before idling.
Write-Output "INBOX NOW (read anything newer than your last ACK before idling):"
Get-ChildItem $inbox -File | Sort-Object LastWriteTime | Select-Object -Last 5 |
    ForEach-Object { Write-Output ("  {0}  {1}" -f $_.LastWriteTime.ToString('MM-dd HH:mm'), $_.Name) }
$seen = @(Get-ChildItem $inbox -File | Select-Object -ExpandProperty Name)
$boardStamp = (Get-Item $board).LastWriteTimeUtc
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 20
    $now = @(Get-ChildItem $inbox -File | Select-Object -ExpandProperty Name)
    $new = $now | Where-Object { $seen -notcontains $_ }
    if ($new) { Write-Output ("NEW-MESSAGE: " + ($new -join ', ')); exit 0 }
    if ((Get-Item $board).LastWriteTimeUtc -ne $boardStamp) { Write-Output 'BOARD-CHANGED'; exit 0 }
}
Write-Output 'TIMEOUT - run again'
exit 2
