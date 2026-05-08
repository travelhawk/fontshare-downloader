@echo off
echo.
echo ======================================
echo    Fontshare Quick Font Installer
echo ======================================
echo.
echo This will install all downloaded fonts to your system.
echo.
echo Note: You may need administrator privileges for best results.
echo       Right-click and "Run as administrator" if fonts don't install.
echo.
pause

python scripts\legacy\quick_install_fonts.py

echo.
echo Installation process completed!
echo.
pause
