.PHONY: install test api web

install:
	python -m venv .venv
	.venv/Scripts/python -m pip install -e "./backend[dev]"
	cd frontend && npm install

test:
	.venv/Scripts/python -m pytest backend/tests -q

api:
	.venv/Scripts/python -m marketstream

web:
	cd frontend && npm run dev
