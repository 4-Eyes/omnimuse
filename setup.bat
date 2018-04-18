@echo off
:: create the python virtual environment
echo creating python virtual environment
python -m venv omnimuse-env
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

:: activate the venv and install the requirements.txt, then deactivate the virtual environment
echo installing python packages in virtual environment
cmd /c ".\omnimuse-env\Scripts\activate & pip install -r requirements.txt & .\omnimuse-env\Scripts\deactivate"
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

:: install node packages
echo installing node packages
cmd /c "cd .\www\omnimuse\ & npm install & cd .\..\.."
IF %ERRORLEVEL% NEQ 0 GOTO SetupError

exit /B 0

:SetupError
echo Failed to run the setup file. Refer to the README file for further details on setup.
exit /B 1