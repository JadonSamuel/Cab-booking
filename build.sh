#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status.
set -o errexit

# Activate the virtual environment
source env/Scripts/activate

# Generate the requirements.txt file
pip freeze > requirements.txt

# Install dependencies from requirements.txt
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Apply database migrations
python manage.py migrate
