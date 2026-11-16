@echo off
setlocal
rem Run in an x64 MSVC developer prompt with the optional voice runtime installed.
if not defined F125_VOICE_DIR set "F125_VOICE_DIR=%~dp0..\output\tts-q4-bench"
pushd "%F125_VOICE_DIR%\vk3" || exit /b 1
cl /nologo /std:c++17 /EHsc /O2 "%~dp0endpoint.cpp" /Fe:voice-endpoint.exe /link ole32.lib uuid.lib ksuser.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /O2 /I"%F125_VOICE_DIR%\qwentts\src" "%~dp0speaker.cpp" qwen.lib winmm.lib dxgi.lib /Fe:voice-speaker.exe
exit /b %errorlevel%
