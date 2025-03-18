@echo off
REM Check if Git is installed by running "git --version"
git --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Git not found. Attempting to install Git via Chocolatey...
    REM Check if Chocolatey is installed
    choco -v >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo Chocolatey is not installed.
        echo Please install Git manually from https://git-scm.com/downloads or install Chocolatey to automate the process.
        pause
        exit /b 1
    ) else (
        choco install git -y
        REM Verify installation again
        git --version >nul 2>&1
        if %ERRORLEVEL% neq 0 (
            echo Git installation failed. Please install Git manually.
            pause
            exit /b 1
        )
    )
) else (
    echo Git is already installed.
)

REM Clone the repository from GitHub if it hasn't been cloned already.
if not exist "order-management" (
    git clone https://github.com/curioserve/order-management.git
)

REM Change directory to the cloned repository.
cd order-management

REM Install the required Python packages.
pip install -r requirements.txt

REM Run the Flask application.
python app.py

pause