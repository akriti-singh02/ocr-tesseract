@echo off
REM Double-click to share the full app (with LaBSE / BGE-M3) from this computer through a public link.
REM The link works only while this window stays open. It changes every time you start it.
cd /d "%~dp0"

set CF=cloudflared
where cloudflared >nul 2>nul || (
    if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (set CF="%ProgramFiles(x86)%\cloudflared\cloudflared.exe") else (
    if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (set CF="%ProgramFiles%\cloudflared\cloudflared.exe") else (
        echo Installing Cloudflare Tunnel (one time only^)...
        winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
        set CF="%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
    ))
)

start "PDF to dataset (app)" python -m streamlit run app.py --server.port 8501 --server.headless true
echo.
echo Starting the public link. Look below for a line ending in  .trycloudflare.com
echo Send that link to your teammate. Close this window to stop sharing.
echo.
%CF% tunnel --url http://localhost:8501
pause
