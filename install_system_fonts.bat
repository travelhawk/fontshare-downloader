@echo off
echo.
echo ========================================
echo     System Font Installer (Admin)
echo ========================================
echo.
echo This will install fonts system-wide for all users.
echo Requires administrator privileges.
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Running as Administrator
) else (
    echo ❌ This script must be run as Administrator!
    echo.
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

echo.
echo Installing fonts to C:\Windows\Fonts...
echo.

python scripts\legacy\install_system_fonts.py

echo.
echo Installation completed!
echo.
pause
