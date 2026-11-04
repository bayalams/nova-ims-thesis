SHELL := /bin/bash

.PHONY: help test collector-all collect-all

help:
	@echo "Available commands:"
	@echo "  make test          Run the Python test suite"
	@echo "  make collector-all Run the full collector pipeline for all sources"
	@echo "  make collect-all   Alias for collector-all"

test:
	uv run test

collector-all:
	bash collector/run_all_sources_pipeline.sh

collect-all: collector-all
