# KorriSco Game Catalog

Official public game configuration catalog for KorriSco.

This repository contains:
- the game catalog index;
- individual game configurations;
- game illustrations;
- the JSON schema used to validate catalog contributions.

## Structure

- `catalog.json` — catalog index
- `games/` — individual game configurations
- `images/` — game illustrations
- `schema/` — JSON schema definitions

The catalog is consumed by KorriSco as a read-only public resource.
Imported games become independent local copies in the application.
