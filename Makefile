.PHONY: test demo

PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

demo:
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli serve-product \
		--elder-ref demo-elder --device-ref demo-c6c --host 127.0.0.1 \
		--port 8765 --store-root /tmp/kangshield-submission-demo --demo
