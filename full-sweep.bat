@echo off
REM Full sweep across every platform and every board, ignoring tiering.
REM 40-60 minutes. Run this roughly weekly, or whenever a --fast run looks thin.
REM
REM The daily --fast run skips Workday and the enterprise ATS platforms
REM (iCIMS, SuccessFactors, Taleo, Eightfold, Jobvite). Those took 143,847
REM postings to yield 4 hits, so they are not worth 45 minutes every day -
REM but they are worth checking now and then.

cd /d "%~dp0scanner"
python refresh.py --all
echo.
echo ============================================================
echo  Full sweep complete. Board written to:
echo    %~dp0target_board.html
echo ============================================================
echo.
pause
