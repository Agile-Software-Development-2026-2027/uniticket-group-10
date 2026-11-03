# Start the local demo and show only new receiver messages.
Push-Location -LiteralPath $PSScriptRoot
try {
    $startupOutput = & docker compose -f compose.receiver-demo.yml up --build -d 2>&1
    if ($LASTEXITCODE -ne 0) {
        $startupOutput | ForEach-Object { Write-Host $_ }
        throw 'Avvio della demo fallito. Controlla che Docker Desktop sia aperto.'
    }
    $insideEvent = $false
    & docker compose -f compose.receiver-demo.yml logs --follow --tail 150 --no-log-prefix lab |
        ForEach-Object {
            if ($_ -match '^\[TICKET EVENT\] \{$') { $insideEvent = $true }
            if ($insideEvent) {
                Write-Host $_
                if ($_ -eq '}') { $insideEvent = $false; Write-Output '' }
            }
        }
}
finally {
    Pop-Location
}
