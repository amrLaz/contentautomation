# Template de script faceless (compatible MoneyPrinterTurbo)

Durée cible : 30-45 s (~80-120 mots narrés) sauf si les stats de la chaîne montrent mieux ailleurs.

## Structure
**Hooks (3 variantes, 1 retenue)**
1. ...  2. ...  3. ...  -> retenu : N (pourquoi)

**Corps** (scène par scène)
| # | Texte narré | Mots-clés visuels (EN, 2-3 mots) | Texte à l'écran |
|---|---|---|---|

**Fin / CTA** : une seule action, formulée naturellement.

**Méta** : Titre · Description · Hashtags (3-5) · Date/heure de publication suggérée

## Passage à MoneyPrinterTurbo
L'outil accepte un sujet, un script rédigé et des mots-clés de recherche de vidéos, plus des options (format vertical 9:16, voix, sous-titres, musique). Fournis :
- `video_subject` : le sujet en une phrase
- `video_script` : le texte narré complet (sans notes de mise en scène ni numéros)
- `video_terms` : mots-clés visuels en anglais, séparés par des virgules (les banques de stock fonctionnent surtout en anglais)
- Réglages constants pour toute la chaîne : voix, style de sous-titres, aspect 9:16, musique (cohérence de marque)

Les noms exacts des champs de l'API peuvent changer selon la version : vérifie-les dans la documentation de l'API de l'instance installée (page /docs de l'API) avant d'automatiser, et dis à l'utilisateur de le faire si tu ne peux pas.

## Règles d'écriture
- Phrases courtes, mots simples, une idée par phrase.
- Premier mot utile dès la première seconde : pas d'introduction.
- Les mots-clés visuels décrivent ce qu'on VOIT à cet instant, pas le concept abstrait.
- Écris pour l'oreille : lis mentalement à voix haute, supprime ce qui sonne écrit.

## Variante quiz (rendu local, sans MoneyPrinterTurbo)
Pour une chaîne de quiz, MoneyPrinterTurbo ne convient pas (narration sur stock, pas de gabarit question/options/chrono). Dans le dépôt `contentautomation`, utilise `tools/render_quiz.py` avec un fichier `quizzes/<sujet>.json` (accroche, questions à 2-4 options, réponse, note de réponse, CTA). Le rendu est un Short 9:16 muet d'environ 33 s, lisible sans le son. Il refuse tout quiz contenant `[à vérifier]` (porte Exactitude) ou une option trop longue. La voix off est une étape séparée, optionnelle.
