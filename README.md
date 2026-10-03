# KorriSco Game Catalog

Catalogue public officiel de configurations de jeux pour KorriSco. Ce dépôt est autonome : l’application Flutter le consomme en lecture seule, puis chaque jeu importé devient une copie locale indépendante.

## Structure

- `catalog.json` — index public et métadonnées utilisées par la liste ;
- `games/` — une configuration JSON détaillée par jeu ;
- `images/` — illustrations optionnelles (aucune image n’est requise pour les fixtures actuelles) ;
- `schema/game.schema.json` — contrat JSON Schema Draft 2020-12 des configurations ;
- `scripts/validate_catalog.py` — validation de l’index, des fichiers et des règles entre champs.

## Format V1

Les identifiants sont en lowercase kebab-case ASCII, par exemple `relais-chronometre`. Les chemins sont relatifs et les configurations détaillées utilisent `schemaVersion: 1`. Les propriétés additives inconnues restent autorisées ; `scoreStep` est explicitement interdit.

Les manches se configurent de trois façons : `rounds.enabled: false` signifie qu’il n’y a pas de manches ; `rounds.enabled: true` avec un entier `count` de 2 à 99 définit un nombre fixe ; `rounds.enabled: true` avec `count: null` indique que les tours sont ajoutés progressivement pendant la partie.

`catalogVersion` est une chaîne opaque. Elle doit changer lorsqu’une modification de contenu publié doit pouvoir être identifiée par le client. La première version publiée d’un jour utilise `YYYY-MM-DD`, puis les mises à jour supplémentaires du même jour utilisent un suffixe ordinal, par exemple `2026-10-03.1`, puis `2026-10-03.2`. Aucune comparaison SemVer n’est définie.

## Ajouter un jeu

1. Créer `games/<id>.json` avec un identifiant lowercase kebab-case.
2. Ajouter l’entrée correspondante dans `catalog.json`, avec `id`, `name`, `players` et `path: "games/<id>.json"`.
3. Ajouter éventuellement une illustration originale dans `images/<id>.webp` et référencer exactement ce même chemin dans `catalog.json` et `games/<id>.json`. Le fichier doit être un WebP de 256×256 pixels et peser au maximum 100 Ko ; une taille inférieure à 50 Ko est recommandée. L’image est facultative : l’application utilise son fallback lorsqu’elle est absente. Les images source haute définition ne sont pas destinées à être distribuées directement par le Catalogue. Le Catalogue est strict pour les nouvelles images WebP, tandis que l’application reste tolérante et peut lire les anciens PNG/JPEG.
4. Mettre à jour `catalogVersion` si le contenu publié change.
5. Lancer `python -m pip install -r requirements.txt`, puis `python scripts/validate_catalog.py`.

Les illustrations doivent être originales ou utilisées avec les droits/licences appropriés. Ne pas copier les visuels commerciaux officiels ni reproduire intégralement les règles d’un éditeur ; les descriptions doivent rester originales et concises. N’ajouter aucun secret ni token.

Les contributions passent par une pull request. La CI vérifie les JSON, le schéma, les chemins, les doublons, les fichiers orphelins, les images référencées et la cohérence entre index et détail.

## Préparer une illustration

Les mainteneurs peuvent préparer une source PNG, JPEG ou WebP carrée avec Pillow avant publication :

```sh
python scripts/prepare_image.py ~/Desktop/scrabble.png scrabble
```

Le script crée `images/scrabble.webp` en 256×256 pixels, avec une taille maximale de 100 Ko. Il vise une taille inférieure à 50 Ko, conserve la source intacte et refuse les sources non carrées ou plus petites que 256×256. Une destination existante est refusée par défaut ; utiliser `--force` pour la remplacer explicitement :

```sh
python scripts/prepare_image.py ~/Desktop/scrabble.png scrabble --force
```

Cette préparation ne modifie ni `catalog.json`, ni `games/<id>.json`, ni `catalogVersion`. Après vérification du rendu, ajouter explicitement la même référence `images/<id>.webp` dans les deux JSON et mettre à jour `catalogVersion` lors de la publication réelle. Conserver les sources haute définition hors des fichiers distribués.

## Validation locale

```sh
python -m pip install -r requirements.txt
python scripts/validate_catalog.py
```

La validation ne nécessite ni Flutter, ni Dart, ni service réseau.
