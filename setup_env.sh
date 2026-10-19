#!/usr/bin/env bash

set -e

ENV_NAME="pitchbooking"

echo "Creating or updating Conda environment..."

conda env update -f environment.yml --prune || conda env create -f environment.yml

echo "Installing Python dependencies..."

conda run -n "$ENV_NAME" python -m pip install -r requirements.txt

echo ""
echo "PitchBooking environment ready!"
echo ""
echo "Activate with:"
echo "conda activate $ENV_NAME"