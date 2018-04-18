REM create the python virtual environment
echo "creating python virtual environment"
python -m venv omnimuse-env
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

REM activate the venv and install the requirements.txt, then deactivate the virtual environment
echo "installing python packages in virtual environment"
.\omnimuse-env\Scripts\activate
pip install -r requirements.txt
.\omnimuse-env\Scripts\deactivate.bat
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

REM install node packages
echo "installing node packages"
cd .\www\omnimuse\
npm install
cd .\..\..
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

exit /B 0

:SetupError
echo "Failed to run the setup file. Refer to the README file for further details on setup."
exit /B 1