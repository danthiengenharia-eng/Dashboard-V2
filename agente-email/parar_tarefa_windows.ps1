# Para o agente e remove a inicialização automática.
Stop-ScheduledTask -TaskName "AgenteEmailDanthi" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "AgenteEmailDanthi" -Confirm:$false -ErrorAction SilentlyContinue
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*pythonw*" } | Stop-Process -Force
Write-Host "Agente parado e removido da inicialização."
pause
