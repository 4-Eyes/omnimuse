# Omnimuse

## Development

### Setup
If running on Windows, running the setup.bat file should set up your environment for development. If running Linux, use the equivalent <span>setup.sh</span> file.

Should it fail to complete then run the following commands:

1. Create a new python virtual environment. Run the following command:
```
> python -m venv omnimuse-env
```
2. Activate the virtual environment and install the python packages in the requirements.txt file:
```
> .\omnimuse-env\Scripts\activate
> pip install -r requirements.txt
```
3. Install the npm packages for the websites:
```
> cd www\omnimuse
> npm install
```

### Running the Site

There are two parts to this website:
1. The back end. Developed in python using the Django framework
2. The front end. Which consists of a number of Angular apps.

Depending on which part of the program you're working on you'll need to run one, or all of the three detailed below:
1. The Django backend. Run this by executing the following command (while the virtual environment is active) in the `omnimusesite` directory.
```
> python manage.py runserver
```
2. Configuration website. To run this in development mode, where file changes are compiled as they happen, run the following command in `www\omnimuse` directory.
```
> ng build configuration --watch
```
3. Generation website. Run the same command as in step 2, but swap `configuration` with `generation`.