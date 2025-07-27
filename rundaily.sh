#!/bin/bash

# Path to your virtual environment
VENV_PATH="/home/art3m1sf0wl/program/street_cars/myenv/bin/activate"

# Path to your Python script
PYTHON_SCRIPT="/home/art3m1sf0wl/program/street_cars/app1.py"

# Function to run the script
run_script() {
    echo "$(date): Starting script execution"
    
    # Source the virtual environment
    source "$VENV_PATH"
    
    # Run the Python script
    python3 "$PYTHON_SCRIPT"
    
    # Deactivate the virtual environment
    deactivate
    
    echo "$(date): Script execution completed"
}

# Main loop
while true; do
    # Get current time
    current_time=$(date +%H:%M)
    
    # Check if it's midnight (00:00)
    if [ "$current_time" == "03:00" ]; then
        run_script
        
        # Sleep for 1 minute to avoid multiple executions at midnight
        sleep 60
    fi
    
    # Sleep for 1 minute before checking again
    sleep 60
done
