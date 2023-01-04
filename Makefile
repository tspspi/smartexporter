all:

build: src/zfsexporter/zfsexporter.py src/zfsexporter/__init__p.y setup.cfg pyproject.toml

	python -m build

.PHONY: all
