python3 -m venv omnimuse-env

chmod +x ./omnimuse-env/bin/activate && source ./omnimuse-env/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt && deactivate

cd ./www/omnimuse/ && npm install && cd ./../..