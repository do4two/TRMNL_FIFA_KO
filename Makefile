PY=.venv/bin/python

.PHONY: setup build build-offline simulate preview preview-png test all
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

build:          ## fetch live openfootball data -> output/trmnl_data.json
	$(PY) src/build_data.py

build-offline:  ## use cached data/ files (no network)
	$(PY) src/build_data.py --matches data/worldcup.json --teams data/worldcup.teams.json

simulate:       ## fill the bracket from data/simulate_full.json (demo a played-out tree)
	$(PY) src/build_data.py --matches data/worldcup.json --teams data/worldcup.teams.json \
		--simulate data/simulate_full.json

preview:        ## render the 4 layouts to preview/*.html
	$(PY) src/render_preview.py

preview-png:    ## render the 4 layouts to preview/*.html + *.png (needs Google Chrome)
	$(PY) src/render_preview.py --png

test:
	$(PY) tests/test_bracket.py
	$(PY) tests/test_markup.py

all: test build preview
