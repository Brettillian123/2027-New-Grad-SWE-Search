@echo off
REM Daily board refresh. Double-click this, or run it from a terminal.
REM ~4-5 minutes. Costs nothing but time - no AI tokens are used.
REM
REM Prints: what posted in the last 48 hours, and what is new since last run.
REM Then open target_board.html in a browser, or ask Claude to publish it.

cd /d "%~dp0scanner"
python refresh.py --fast
echo.
echo ============================================================
echo  Board written to: %~dp0target_board.html
echo  CSV written to:   %~dp0newgrad_2027_targets.csv
echo.
echo  Anything worth applying to? Tell Claude:
echo    "refresh the board"        - I re-run this and publish the artifact
echo    "tailor for ^<company^>"     - one resume against that posting
echo ============================================================
echo.
pause
