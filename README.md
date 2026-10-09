# KorriSco Game Catalog

Catalogue public officiel de configurations de jeux pour KorriSco. Le dépôt est autonome : l’application le consomme en lecture seule, puis chaque jeu importé devient une copie locale indépendante.

## Contrat V2

`catalog.json` est l’index V2 publié et utilise `schemaVersion: 2`. Il contient uniquement les métadonnées nécessaires à l’affichage, à la recherche, au tri, à la compatibilité et à la localisation de la fiche détaillée. Une fiche est chargée uniquement lorsqu’un jeu est sélectionné/importé.

Chaque entrée contient au minimum :

- `id` : identifiant lowercase kebab-case ASCII ;
- `name` ;
- `path` : chemin relatif explicite vers `games/<id>.json` ;
- `players` ;
- `playMode` (`individual` ou `teams`) ;
- `requiredCapabilities`.

Les métadonnées facultatives d’index sont `icon`, `image` et `minimumAge`. Les règles utilisateur et `gameRules` appartiennent exclusivement à la fiche `games/<id>.json`. Les métadonnées répétées dans l’index et la fiche sont contrôlées par le validateur afin d’éviter les divergences.

Chaque fiche `games/<id>.json` est une définition V2 complète : `schemaVersion`, identité, joueurs, mode, capabilities, métadonnées éventuelles, `gameRules` et règles utilisateur. Elle peut utiliser `gameRules.type: standard` ou `declarative`. Le Catalogue valide la structure et les images ; l’application Flutter reste l’autorité finale pour l’adaptation exacte en `GameDefinition` et les règles déclaratives.

`catalogVersion` est une chaîne opaque. Elle change lorsqu’un contenu publié change. La convention est `YYYY-MM-DD` pour la première publication d’une journée, puis `YYYY-MM-DD.1`, `.2`, etc. Aucune comparaison SemVer n’est définie.

## Images

Une image est facultative. Lorsqu’elle est publiée, elle doit être référencée par `image: "images/<id>.webp"`, être un WebP réel de 256×256 pixels et peser au maximum 100 KiB. Une taille inférieure à 50 KiB est recommandée. Le fallback visuel de l’application est utilisé en l’absence d’image.

Les images source haute définition ne sont pas distribuées directement par le Catalogue. Elles doivent rester hors du dépôt. Les illustrations publiées doivent être originales ou utilisées avec les droits/licences appropriés ; les visuels commerciaux et les règles copiées intégralement ne doivent pas être ajoutés.

## Ajouter un jeu

1. Créer `games/<id>.json` avec une définition V2 complète.
2. Ajouter dans `catalog.json` l’entrée d’index avec son `path` explicite.
3. Choisir `standard` ou `declarative` selon le contrat existant ; ne pas inventer de nouveaux champs.
4. Ajouter éventuellement `images/<id>.webp` et référencer le même chemin dans l’index et la fiche.
5. Incrémenter `catalogVersion` lors de la publication.
6. Exécuter la validation locale.

Le chargement de l’index ne télécharge pas les fiches. Lors de l’import, seule la fiche sélectionnée est téléchargée puis snapshotée dans le jeu local ; une modification ou suppression distante ne modifie donc pas une partie déjà importée. Les fiches ne disposent pas d’un cache métier distinct obligatoire : le cache existant peut servir de repli réseau, puis le snapshot local assure l’autonomie du jeu.

Cette séparation garde `catalog.json` léger lorsque le Catalogue passe de quelques jeux à plusieurs dizaines ou centaines, sans embarquer toutes les règles métier dans chaque chargement de liste.

## Préparer une illustration

Les mainteneurs peuvent convertir une source PNG, JPEG ou WebP carrée avec Pillow :

```sh
python scripts/prepare_image.py ~/Desktop/scrabble.png scrabble
```

Le script produit `images/scrabble.webp` en 256×256 pixels, sans modifier la source. Une destination existante est refusée par défaut ; utiliser `--force` pour la remplacer explicitement.

## Validation locale

```sh
python -m pip install -r requirements.txt
python scripts/validate_catalog.py
python -m unittest discover -s tests
```

La validation ne nécessite ni Flutter, ni Dart, ni service réseau. La CI GitHub exécute ces mêmes contrôles sur chaque `push` et `pull_request`.
