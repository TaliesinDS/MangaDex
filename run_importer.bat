@echo off
:: Simple front-end wrapper for import_mangadex_bookmarks_to_suwayomi.py
:: Makes it easier for non-technical users on Windows.
:: Author: Generated helper

setlocal ENABLEDELAYEDEXPANSION

echo ===============================================
echo  MangaDex -> Suwayomi Import Helper
echo ===============================================

:: Locate Python
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found in PATH. Please install Python from https://www.python.org/downloads/ and check 'Add to PATH'.
  pause
  goto :eof
)

:: Base URL
set BASE_URL=
set /p BASE_URL=Enter Suwayomi base URL (e.g. http://localhost:4567) : 
if "%BASE_URL%"=="" (
  echo Base URL is required.
  pause
  goto :eof
)

:: Follows fetch?
set FROM_FOLLOWS=
set /p FROM_FOLLOWS=Fetch all MangaDex follows? (Y/N) [Y]: 
if /I "%FROM_FOLLOWS%"=="" set FROM_FOLLOWS=Y

:: MangaDex credentials (only if FROM_FOLLOWS=Y)
set MD_USER=
set MD_PASS=
if /I "%FROM_FOLLOWS%"=="Y" (
  set /p MD_USER=MangaDex username : 
  if "%MD_USER%"=="" (
     echo Username required when fetching follows.
     pause
     goto :eof
  )
  set /p MD_PASS=MangaDex password (input hidden not supported in .bat) : 
)

:: Reading status mapping
set IMPORT_STATUS=
set /p IMPORT_STATUS=Import reading statuses and map to categories? (Y/N) [Y]: 
if /I "%IMPORT_STATUS%"=="" set IMPORT_STATUS=Y
set STATUS_MAP=
if /I "%IMPORT_STATUS%"=="Y" (
  echo Example map: completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9
  set /p STATUS_MAP=Enter status->category map (leave blank to skip mapping) : 
)

:: Chapter read markers
set IMPORT_CHAPTERS=
set /p IMPORT_CHAPTERS=Import chapter read markers? (Y/N) [N]: 
if /I "%IMPORT_CHAPTERS%"=="" set IMPORT_CHAPTERS=N
set READ_DELAY=0
if /I "%IMPORT_CHAPTERS%"=="Y" (
  set /p READ_DELAY=Delay (seconds) after adding each manga before syncing chapters [1]: 
  if "%READ_DELAY%"=="" set READ_DELAY=1
)

:: Category ID (optional)
set CATEGORY_ID=
set /p CATEGORY_ID=Single category id to also assign to every manga (optional): 

:: Dry run first?
set DRY_RUN=
set /p DRY_RUN=Dry run (no changes) first? (Y/N) [Y]: 
if /I "%DRY_RUN%"=="" set DRY_RUN=Y

:: Follows JSON path
set FOLLOWS_JSON=follows_output.json
set /p FOLLOWS_JSON=Output JSON file for fetched follows [follows_output.json]: 
if "%FOLLOWS_JSON%"=="" set FOLLOWS_JSON=follows_output.json

:: Build command
set CMD=python "import_mangadex_bookmarks_to_suwayomi.py" --base-url "%BASE_URL%"
if /I "%FROM_FOLLOWS%"=="Y" set CMD=%CMD% --from-follows --md-username "%MD_USER%" --md-password "%MD_PASS%" --follows-json "%FOLLOWS_JSON%"
if /I "%IMPORT_STATUS%"=="Y" set CMD=%CMD% --import-reading-status
if /I "%IMPORT_STATUS%"=="Y" if not "%STATUS_MAP%"=="" set CMD=%CMD% --status-category-map "%STATUS_MAP%"
if /I "%IMPORT_CHAPTERS%"=="Y" set CMD=%CMD% --import-read-chapters --read-sync-delay %READ_DELAY%
if not "%CATEGORY_ID%"=="" set CMD=%CMD% --category-id %CATEGORY_ID%
if /I "%DRY_RUN%"=="Y" set CMD=%CMD% --dry-run

echo.
echo Running:
echo %CMD%
echo.
%CMD%

echo.
echo ===============================
echo  Run Complete
if /I "%DRY_RUN%"=="Y" (
  echo Dry run finished. Run again without dry-run? (Y/N) [N]:
  set AGAIN=
  set /p AGAIN=:
  if /I "%AGAIN%"=="Y" (
     set CMD=%CMD: --dry-run=%
     echo Running real import:
     echo %CMD%
     %CMD%
  )
)

echo Done.
pause
endlocal
