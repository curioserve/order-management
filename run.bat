@echo off
REM Clone the repository from GitHub if it hasn't been cloned already.
if not exist "order-management" (
    git clone https://github.com/curioserve/order-management.git
)

REM Change directory to the cloned repository.
cd order-management

REM Install the required Python packages.
pip install -r requirements.txt

REM Run the Flask application.
REM Adjust the command below if your app file is named differently.
python app.py

pause
