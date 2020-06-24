#!/bin/sh

# `python3 -m pip install coverage` or `sudo apt install python3-coverage`

python3 -m coverage run test_cals2sim.py && \
	python3 -m coverage report -m && \
	python3 -m coverage html
