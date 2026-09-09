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
    Add-Content $log "$ts starting collector"
    $p = Start-Process python -ArgumentList '-u','-m','option-lab.collector.run_collector','--auto' -WorkingDirectory $wd -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
    Set-Content -Path $pidf -Value $p.Id
    $started = Get-Date
    $p.WaitForExit()
    $dur = ((Get-Date) - $started).TotalSeconds
    Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exited code=$($p.ExitCode) dur=$([math]::Round($dur,1))s"
    if ($dur -lt 60) { $fails++; } else { $fails = 0; }
    if ($fails -ge 5) {
        Add-Content $log "5 rapid failures - backing off 600s (token may be expired)"
        Start-Sleep 600
        $fails = 0
    } else {
        Start-Sleep 15
    }
}