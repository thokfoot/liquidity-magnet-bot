$ErrorActionPreference = 'SilentlyContinue'
$wd = 'C:\Dev\Dev\Trading'
$log = 'C:\Users\Mind\AppData\Local\Temp\opencode\watchdog.log'
$pidf = 'C:\Users\Mind\AppData\Local\Temp\opencode\collector_gcs.pid'
$out = 'C:\Users\Mind\AppData\Local\Temp\opencode\collector_gcs.log'
$err = 'C:\Users\Mind\AppData\Local\Temp\opencode\collector_gcs.err'

$env:GCS_BUCKET = 'trading-backup-sonic-airfoil-507912'
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\Users\Mind\Downloads\sonic-airfoil-507912-h0-7e38a438bee7.json'
$env:PYTHONUNBUFFERED = '1'

$fails = 0
while ($true) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content $log "$ts starting collector + paper"
    $p = Start-Process python -ArgumentList '-u','-m','option-lab.collector.run_collector','--auto' -WorkingDirectory $wd -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
    Set-Content -Path $pidf -Value $p.Id
    $paperOut = 'C:\Users\Mind\AppData\Local\Temp\opencode\paper.log'
    $paperErr = 'C:\Users\Mind\AppData\Local\Temp\opencode\paper.err'
    $paper = Start-Process python -ArgumentList '-u','C:\Dev\Dev\Trading\option-lab\paper\paper_trader.py','daemon' -WorkingDirectory $wd -RedirectStandardOutput $paperOut -RedirectStandardError $paperErr -WindowStyle Hidden -PassThru
    $started = Get-Date
    while ($true) {
        Start-Sleep 15
        if ($p.HasExited -or $paper.HasExited) { break }
    }
    $collExit = if ($p.HasExited) { "code=$($p.ExitCode)" } else { "killed-by-watchdog" }
    $paperExit = if ($paper.HasExited) { "code=$($paper.ExitCode)" } else { "killed-by-watchdog" }
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    if (-not $paper.HasExited) { Stop-Process -Id $paper.Id -Force }
    $dur = ((Get-Date) - $started).TotalSeconds
    Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') stopped dur=$([math]::Round($dur,1))s collector=$collExit paper=$paperExit"
    if ($dur -lt 60) { $fails++; } else { $fails = 0; }
    if ($fails -ge 5) {
        Add-Content $log "5 rapid failures - backing off 600s (token may be expired)"
        Start-Sleep 600
        $fails = 0
    } else {
        Start-Sleep 15
    }
}