#!/usr/bin/env bash

set -e

ENV_NAME="pitchbooking"

echo "Creating Conda environment..."

conda env create -f environment.yml || {
    echo "Environment may already exist."
}

echo "Installing Python dependencies..."

conda run -n "$ENV_NAME" python -m pip install -r requirements.txt

echo ""
echo "PitchBooking environment ready!"
echo ""
echo "Activate with:"
echo "conda activate $ENV_NAME"