# channel-state.md (mis à jour le 2026-10-13)

## Positionnement (verrouillé)
- Niche : quiz en français
- Sous-niche : France (géographie, histoire, patrimoine, départements, villes)
- Angle : série de 3 questions, du facile à « presque impossible », avec une anecdote vérifiable dans chaque réponse
- Cible : francophones curieux, 18-45 ans, qui commentent leur score
- Promesse : « Tu te crois fort en France ? Teste-toi en 30 secondes. »
- Plateformes / langue : YouTube Shorts + Instagram Reels / français
- Chaîne YouTube : @thisisit9182 (non vérifiée depuis cet environnement, YouTube inaccessible)

## Voix de marque
- Ton : direct, complice, sans prétention (à confirmer avec l'utilisateur)
- Voix de synthèse / réglages MoneyPrinterTurbo : à définir (rien d'installé). Rendu quiz : `tools/render_quiz.py` (Pillow + ffmpeg, muet, 9:16, ~33 s) à partir de `quizzes/*.json`. MoneyPrinterTurbo écarté pour ce format. Voix off : pas encore choisie (aucun TTS installé ici)
- Style visuel / sous-titres : lisible sans le son, question et options en texte à l'écran

## Critères de décision du lot test (valeurs de départ, hypothèses arbitraires)
- Nombre de vidéos : 10, sur 2 à 4 semaines
- Seuil de succès : au moins 3 vidéos sur 10 au-dessus de 1,5 x la médiane de vues du lot ET rétention moyenne des 5 dernières supérieure à celle des 5 premières
- Si succès : garder la niche, doubler sur les formats gagnants. Échec partiel : changer UN facteur et refaire 10 vidéos. Échec net après 2 lots : rouvrir la Phase 2

## Risques identifiés
- n°1 : contenu « inauthentique / répétitif » (politique de monétisation YouTube, à vérifier sur la page officielle)
- n°2 : erreur factuelle dans une réponse (toute réponse doit être sourcée)
- Droits : images (Wikimedia Commons, licences à noter), pas de musique protégée
- Données : Semrush sans unités d'API (2026-10-13), aucune donnée de vues sur chaînes quiz francophones

## Formats gagnants
- (aucun, chaîne vierge)

## Formats perdants
- (aucun)

## Log des vidéos
| Date | Titre | Hook utilisé | Durée | Score critique | Vues | Rétention | Abonnés + | Notes |
|---|---|---|---|---|---|---|---|---|

## Idées en réserve
- (à remplir en Phase 3)

## État du lot 1
- Gévaudan : prêt (36/45), `quizzes/gevaudan.json` rendu OK
- Catacombes : rendu OK, 33/45 sous le seuil, à améliorer (hook chiffré, bouclage)
- Carnac : boucle 2 faite, 34/45, rendu OK, sources non officielles
- Rien n'est publié ni programmé

## Hypothèses à tester au prochain lot
- Le format « échelle de difficulté » retient mieux qu'un quiz à une seule question
- Un habillage saisonnier (Halloween/Toussaint, 11 novembre) booste-t-il les vues de départ ?
