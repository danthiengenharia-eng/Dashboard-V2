# Registra o agente para iniciar sozinho ao entrar no Windows, sem janela, e reiniciar se parar.
# Uso: clique com o botão direito neste arquivo > "Executar com o PowerShell".
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $exe) { Write-Host "pythonw.exe não encontrado. Reinstale o Python marcando 'Add Python to PATH'."; pause; exit 1 }
$acao = New-ScheduledTaskAction -Execute $exe -Argument "-m agente_email --loop" -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "AgenteEmailDanthi" -Action $acao -Trigger $gatilho -Settings $config -User $env:USERNAME -Force | Out-Null
Start-ScheduledTask -TaskName "AgenteEmailDanthi"
Write-Host "Pronto. O agente está rodando em segundo plano e iniciará sozinho com o Windows."
Write-Host "Para acompanhar: abra $pasta\saida\agente.log"
pause
