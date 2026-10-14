@echo off
REM Double-click to open the PDF-to-text app in your web browser.
cd /d "%~dp0"
python -m streamlit run app.py
pause
