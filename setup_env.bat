@echo off

set ENV_NAME=pitchbooking

echo Creating or updating Conda environment...

call conda env update -f environment.yml --prune || call conda env create -f environment.yml

echo Installing Python dependencies...

call conda run -n %ENV_NAME% python -m pip install -r requirements.txt

echo.
echo PitchBooking environment ready!
echo.
echo Activate with:
echo conda activate %ENV_NAME%

pause