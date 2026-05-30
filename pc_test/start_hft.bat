@echo off
TITLE HFT System Launcher
color 0A

:: Bu dizine gec
cd /d "%~dp0"

echo ===================================================
echo       FPGA HFT ACCELERATOR - SYSTEM LAUNCHER
echo ===================================================
echo.

echo [1/2] C++ HFT Motoru (Daemon) baslatiliyor...
:: Arka planda yeni bir pencerede motoru calistir
start "C++ HFT Engine (Backend)" cmd /k "hft_engine.exe"

echo Motorun 5005 portunu hazirlamasi icin 1 saniye bekleniyor...
timeout /t 1 /nobreak > nul

echo [2/2] Python Frontend (Arayuz) baslatiliyor...
:: Arayuzu calistir (pythonw kullanmiyoruz ki eger hata olursa siyah ekranda gorebilelim)
start "Python Frontend" python hft_frontend.py

echo.
echo Sistem basariyla baslatildi. Bu pencere 3 saniye icinde kapanacak.
timeout /t 3 /nobreak > nul
exit
