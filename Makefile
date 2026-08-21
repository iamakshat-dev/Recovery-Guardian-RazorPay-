.PHONY: install data initdb train run test clean

install:
	pip install -r requirements.txt

data:
	cd data && python3 generate_data.py --rows 1500 --burst-rows 110 --seed 42 --out synthetic_events.csv

initdb:
	python3 src/db.py

train:
	python3 -m src.model.training

run:
	uvicorn src.api.app:app --reload

test:
	pytest tests/ -v

clean:
	rm -f recovery_guardian.db
	rm -f data/synthetic_events.csv
	rm -rf artifacts/
