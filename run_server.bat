@echo off
title Pharma Search Server
cd /d "%~dp0"
echo ==========================================
echo   Pharma Product Search — Server
echo ==========================================
echo.
echo Starting server... (loading data, ~15s)
echo DO NOT CLOSE THIS WINDOW.
echo.
python web.py
echo.
echo Server stopped. Press any key to exit.
pause
