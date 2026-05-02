@echo off
setlocal
cd /d "%~dp0..\..\.."
:loop
echo.
echo ============================================================
echo Iniciando agentes autonomos Tennis Hub...
echo Data/Hora: %date% %time%
echo ============================================================
echo.
powershell -ExecutionPolicy Bypass -File ".tools\ai-agents\run-autonomous.ps1"
echo.
echo ============================================================
echo O script terminou, caiu ou foi interrompido.
echo Aguardando 10 minutos para reiniciar automaticamente...
echo ============================================================
echo.
timeout /t 600 /nobreak
goto loop
