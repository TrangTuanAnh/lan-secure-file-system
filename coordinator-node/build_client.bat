@echo off
setlocal

cd /d "%~dp0"

echo [1/5] Cleaning old build artifacts...
if exist "dist" rmdir /S /Q "dist"
if exist "build" rmdir /S /Q "build"
if exist "Secure File System.spec" del /F /Q "Secure File System.spec"

echo [2/5] Building desktop client...
pyinstaller --noconfirm --clean --windowed --name "Secure File System" --add-data "assets;assets" --add-data "certs;certs" --add-data "config;config" main.py
if errorlevel 1 goto :build_failed

echo [3/5] Copying runtime .env...
if exist ".env" (
    copy /Y ".env" "dist\Secure File System\.env" >nul
) else (
    echo Warning: .env not found in %cd%
)

echo [4/5] Verifying output...
if not exist "dist\Secure File System\Secure File System.exe" goto :missing_output

echo [5/5] Build completed successfully.
echo Output: "%cd%\dist\Secure File System\Secure File System.exe"
goto :eof

:build_failed
echo Build failed.
exit /b 1

:missing_output
echo Build finished but output exe was not found.
exit /b 1
