PYTHON = python3

.PHONY: sync status translate stamp site-sync dev build check

sync:
	$(PYTHON) scripts/sync.py

status:
	$(PYTHON) scripts/status.py

translate:
	$(PYTHON) scripts/translate.py $(ARGS)

stamp:
	$(PYTHON) scripts/stamp.py $(FILES)

site-sync:
	$(PYTHON) scripts/publish.py
	$(PYTHON) scripts/build_nav.py

dev: site-sync
	cd site && npm run dev

build: site-sync
	cd site && npm run build

check: site-sync
	$(PYTHON) scripts/status.py
