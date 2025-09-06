# !/usr/bin/env bash
# exit on error
# set -o errexit

# Install Python dependencies from requirements.txt
# pip install -r requirements.txt

# Install the Chromium browser required by Playwright
# playwright install chromium


#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt
playwright install chromium
