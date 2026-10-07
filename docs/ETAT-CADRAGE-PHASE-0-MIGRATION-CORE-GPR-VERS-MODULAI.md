# État du cadrage — migration du Core GPR vers ModulAI

**Date de référence : 5 octobre 2026**  
**Statut : Phase 0 clôturée le 5 octobre 2026.**

Ce document consigne les résultats observés en Phase 0 pour intégrer les capacités GPR comme services/modules de la plateforme modulaire ModulAI. Le Core AI ne doit pas contenir de logique métier GPR en dur. Le dépôt `gpr_ai_service` est la base de référence des capacités, pas une plateforme IA concurrente destinée à subsister en parallèle. Aucun code fonctionnel n’est migré dans cette phase.

Voir aussi le [plan d’implémentation de la Phase 0](./PLAN-PHASE-0-CADRAGE-MIGRATION-CORE-GPR-VERS-MODULAI.md) et le [plan général de migration](./PLAN-MIGRATION-CORE-GPR-VERS-MODULAI.md).

## 1. Références des dépôts

Les révisions ont été relevées le 5 octobre 2026. Les états locaux préexistants sont conservés et n’ont pas été réinitialisés.

| Dépôt | Branche | Révision examinée | État de travail observé |
|---|---|---|---|
| GPR `gpr_ai_service` | `develop` | `0c0e54bf96bc61faefd0ac849c30e4f0fba98ad2` | Propre pour les fichiers suivis ; les ressources locales `app/data/` sont ignorées par Git. |
| ModulAI `ai-core-fastapi` | `refactor/simplify-ai-configuration` | `1b0f4d0de1e7654b0833ef7ce25f4715e4758db7` | Changements préexistants : plan de simplification, `main.py`, tests de contrat ; plans de migration non suivis. |
| ModulAI `backend-node` | `refactor/simplify-ai-configuration` | `f2adaefc5c0e8ec8e441c793ed21881eb0a2a49a` | Plan de simplification modifié ; plans de migration non suivis. |
| ModulAI `frontend` | `refactor/simplify-ai-configuration` | `b461c86636549a55e5b1be091ec718eca3d7c3be` | Changements préexistants d’authentification/proxy et plan de simplification ; plans de migration non suivis. |

**Conséquence pour la suite :** les modifications déjà présentes dans ModulAI ne sont pas attribuées à la migration GPR. Aucun de ces changements ne doit être écrasé ni inclus implicitement dans un futur lot de migration.

## 2. Résultats de validation de référence

| Projet et commande | Résultat observé | Interprétation pour la migration |
|---|---|---|
| AI Core ModulAI — `python -m unittest discover -s tests -v` | **3 tests réussis** : payload canonique accepté, resolver avec identifiants/options canoniques, compatibilité legacy. | Base de contrat testée, mais couverture limitée au contrat de configuration ; ne valide pas encore l’exécution d’un module métier. |
| Service GPR — `python -m unittest discover -s tests -v` | **81 tests exécutés : 4 échecs et 2 erreurs.** Les problèmes observés concernent la visualisation et comparaison de requêtes de reporting, une interprétation déterministe, et la ponctuation d’une transcription. | Établir et accepter la baseline avant de comparer une implémentation migrée ; ne pas considérer ces résultats comme causés par la migration. Leurs causes ne sont pas diagnostiquées dans cette phase. |
| Frontend ModulAI — `npm run build` | Build réussi ; Vite signale un chunk JavaScript supérieur à 500 kB. | Build initial valide avec avertissement de taille préexistant, non bloquant pour le cadrage. |
| Backend Node ModulAI | Aucun script de test déclaré dans les scripts du `package.json` examiné. | Définir ultérieurement une stratégie de tests backend/contrat si elle est requise par la migration. |

La suite GPR charge le modèle d’embeddings Sentence-Transformers durant les tests, ce qui a allongé son exécution. Aucun appel réel à un service externe n’est considéré comme validé par cette suite.

## 3. Cartographie des capacités et recouvrements

| Capacité | Implémentation observée côté GPR | Recouvrement ModulAI observé | Écart et frontière proposée |
|---|---|---|---|
| Analyse de réclamation | Routes `/analyze/` et `/analyze/stream`, heuristiques TextBlob/mots sensibles, classification et urgence LLM, résumé et catégories/motifs fournis. | `/api/execute` exécute un use case configuré via le resolver et un provider IA. | Migrer comme module d’analyse avec schémas d’entrée/sortie. Garder catégories, vocabulaire et règles de décision GPR dans sa configuration/extension. |
| Recherche institutionnelle | `/knowledge/search` interroge la collection Chroma `institution_context` ; `/sync/institution` l’alimente avec des documents versionnés. | AI Core a des routes RAG génériques d’extraction, indexation, recherche et inspection ; le resolver sait résoudre des bases de connaissances et des scopes. | Réutiliser les mécanismes RAG génériques, mais définir propriétaires, droits, versions et filtrage de chaque source institutionnelle. |
| Recherche historique et solution | `/search/` et `/search/stream` récupèrent des réclamations similaires dans Chroma, puis demandent une proposition de solution au LLM. | AI Core propose Chroma et recherche sémantique, mais l’indexer générique ne porte pas les règles de feedback GPR. | Créer un module de recherche GPR et un adaptateur d’ingestion ; les règles d’éligibilité des cas historiques restent métier. |
| Transcription | `/transcribe/` accepte audio/texte, utilise une API compatible Whisper distante par défaut, prétraitement FFmpeg facultatif, sélection de vocabulaire, correction, diarisation/structure et payload destiné à la persistance. | Aucun module ou endpoint de transcription identifié dans le Core ModulAI examiné. | Créer un module/provider dédié. Décider du fournisseur, de l’externalisation, de la rétention audio et de la persistance avant l’exposition. |
| Reporting | `/reporting/dashboard` et `/reporting/query`, SQLAlchemy/MySQL ; NLQ interprété en intention puis contrôlé par un catalogue d’opérations et de champs. L’intégration LLM est configurable et peut être déterministe/hybride. | Pas de reporting métier équivalent identifié dans le Core AI ModulAI. Le backend possède des entités projet/module/configuration et des journaux d’API, pas ce modèle analytique GPR. | Isoler schéma et logique métier dans le module GPR et son connecteur. Préserver le catalogue validé ; le modèle ne produit pas de SQL à exécuter. |
| Feedback / apprentissage | `vector_service` ne sélectionne pour l’index historique que les retours `VALIDATED`/`CORRECTED` avec solution retenue. | Le store RAG générique permet l’indexation de documents, mais aucun workflow de feedback validé ni entraînement de modèle identifié. | Migrer éventuellement le feedback comme workflow d’alimentation RAG contrôlé. Ce mécanisme n’est pas du fine-tuning ou de l’apprentissage des poids du LLM. |
| Synchronisation des données | `/sync` racine lance la synchro Java → MySQL ; synchronisation planifiée quotidienne en déploiement. Chroma des réclamations facultatif via `REPORTING_ENABLE_RAG_SYNC`. Endpoints dédiés pour catalogues et documents institutionnels. | ModulAI a un Gateway dynamique et un schéma de ressources de configuration, mais pas le connecteur Java GPR ni ce modèle de sync. | Garder API Java/MySQL dans un adaptateur/worker GPR, avec droits d’exécution, idempotence, reprise et observabilité séparés du Core IA. |
| Audit et observabilité | Corrélation présente sur analyse/recherche ; état et erreurs de sync persistés ; événements structurés de reporting. Certaines routes impriment/loguent le contenu des demandes. | Le Core crée un snapshot de configuration et tente d’écrire un enregistrement d’exécution côté Gateway ; le backend persiste aussi des journaux d’API. | Aligner les IDs de corrélation et champs d’audit sans journaliser les contenus sensibles ; définir rétention, identité et statut de l’écriture d’audit. |

## 4. État de la modularité dans ModulAI

Les fondations de configuration existent :

- Le schéma backend stocke `Module` avec `module_key`, version, use cases, endpoints, data sources, dépendances, capacités et configuration, actuellement majoritairement représentés par des champs `String`/JSON.
- Le Gateway recherche les modules `published`, examine leurs endpoints et associe une requête à un `use_case_key`, puis émet les champs canoniques `module_id`, `module_key`, `use_case_key`, `input` et `request_options`.
- Le Core possède un `ConfigurationResolver` qui résout projet, module, prompt, policy, modèle, provider et RAG et produit un snapshot.
- Le Core expose une orchestration générique `/api/execute`, un provider Ollama et un store Chroma configurable par collection.

**Limite constatée :** la découverte dynamique actuelle sélectionne des endpoints/configurations stockés dans le registre backend ; elle ne démontre pas encore un cycle de vie de plugins exécutables isolés par module. Le Core conserve aussi des champs legacy et un fallback de résolution de prompt. Le modèle de « module métier installable/activable/versionné » doit donc être précisé avant d’implémenter les modules GPR.

**Frontière fonctionnelle retenue — ModulAI reste une plateforme générique :**

- Core AI ModulAI : contrats génériques, validation, résolution de configuration, orchestration, policies, interfaces providers/modules/RAG et traces communes. Il ne contient pas d’imports, clés, prompts, catégories, routes ou logique métier propres à GPR.
- Services/modules GPR : logique de traitement et schémas des use cases métier, enregistrés/configurés dans ModulAI et invoqués via une interface de module générique.
- Connecteurs de données : utilisés par les services/modules qui en ont besoin pour accéder aux sources GPR (par exemple API Java/MySQL). Les détails de ces sources restent hors du Core.
- Infrastructure de données : index, tables, stockage audio et secrets régis par des droits explicites de projet/tenant.

La topologie précise d’hébergement (service séparé ou autre mécanisme d’extension) n’est pas encore arbitrée. Le choix antérieur de handlers chargés dans le processus AI Core est retiré : il ne satisfaisait pas clairement l’exigence de garder le Core indépendant du code GPR.

## 5. Flux fonctionnels de référence

### Exécution générique ModulAI

```text
Client → Backend Gateway
  → endpoint publié/module/use case/configuration du projet
  → payload canonique
  → AI Core /api/execute
  → ConfigurationResolver → prompt/policy/provider/modèle/RAG
  → provider LLM → réponse structurée
  → snapshot/log d’exécution
```

Le Gateway observé transmet aussi des champs legacy pour compatibilité. Le resolver accepte les deux formats ; l’orchestrateur garde un fallback legacy du prompt.

### Analyse GPR

```text
Appelant → POST /analyze/
  → modèle de requête texte + catégories métier facultatives
  → heuristiques sentiment/mots sensibles
  → urgence et classification LLM selon les données fournies
  → résumé + champs métier + correlation_id
```

### Recherche et connaissance GPR

```text
Recherche de réclamations → embedding → collection claims filtrée
  → cas similaires → solutions historiques → génération de proposition

Documents/catégories validés → routes /sync → collections Chroma dédiées
  → /knowledge/search ou contexte de classification
```

### Transcription GPR

```text
Audio/texte → multipart /transcribe/
  → fichier temporaire et prétraitement audio éventuel
  → fournisseur de transcription distant
  → correction/structuration → segments et payload de stockage
  → suppression du fichier temporaire
```

La persistance finale de la transcription côté application n’est pas opérée directement par la route FastAPI examinée.

### Reporting GPR

```text
Question/filtres → intention déterministe ou LLM
  → validation contre catalogue (opérations, cibles, dimensions, limites)
  → requêtes SQLAlchemy sur ReportingClaim
  → réponse, visualisation/comparaison et traces

API Java → synchronisation paginée → MySQL reporting
  → index Chroma facultatif
```

## 6. Registre initial des risques

Évaluation de cadrage seulement, non un audit de sécurité exhaustif.

| Risque | Constat de code initial | Exigence à traiter avant exposition |
|---|---|---|
| Contrôle d’accès API | Aucun guard d’authentification/autorisation FastAPI n’a été trouvé sur les routeurs GPR examinés. Le CORS de `main.py` ne remplace pas un contrôle d’accès. | Authentifier les appels service-à-service et autoriser par projet, module, use case, opération et ressource. |
| Synchronisation/ingestion | La route `/sync` à la racine déclenche la synchro ; `/sync/categories` et `/sync/institution` modifient les index. Les guards d’accès applicatifs n’ont pas été trouvés. | Permissions dédiées, limites, protection contre déclenchements non autorisés, validation des sources et traces d’exécution. |
| Routes RAG AI Core | Les routes index/search/inspect du Core acceptent un nom de collection fourni dans la requête ; le scope de KB est résolu dans l’exécution mais les routes RAG autonomes doivent être considérées séparément. | Restreindre collections et opérations selon l’identité/projet et empêcher les accès croisés. |
| Données sensibles dans les logs | Le code GPR logue un extrait du texte d’analyse, imprime le texte de recherche et les logs de transcription incluent les contenus bruts/corrigés. | Masquage par défaut, IDs de corrélation sans contenu, durée de rétention et accès aux journaux limités. |
| Fournisseurs externes | La transcription transmet l’audio à un endpoint cloud configurable ; certains traitements LLM peuvent aussi utiliser un endpoint distinct. | Décider résidence/consentement, chiffrement, rétention fournisseur, choix de provider, secrets et comportements d’indisponibilité. |
| Isolation des données | Collections GPR sont nommées globalement (`claims`, `categories_motifs`, `institution_context`) et le reporting utilise une base commune ; séparation multi-tenant non démontrée dans l’inventaire. | Définir modèle tenant/projet, partitionnement et tests d’autorisation négatifs avant réutilisation multi-projet. |
| Erreurs et informations exposées | La route de sync racine renvoie le texte de l’exception ; des routes Core convertissent aussi des exceptions en détail HTTP. | Normaliser erreurs publiques et conserver détails diagnostiques dans des logs protégés. |
| Reporting NLQ | L’intention est validée contre un catalogue, ce qui borne l’exécution ; il faut confirmer que chaque voie SQL utilise exclusivement ces constructions et que les filtres d’accès sont appliqués. | Tests de non-régression, limites de résultats/temps et filtrage d’autorisation à chaque requête. |
| Baseline des tests | La suite GPR échoue sur 6 tests sur 81. | Triage et accord explicite sur les anomalies de référence avant les mesures de parité. |

## 7. Cas de référence proposés

Utiliser exclusivement des données synthétiques ou anonymisées. Les entrées et sorties attendues exactes doivent être validées par le métier avant de servir d’oracle de parité.

| ID | Parcours | Cas de référence et vérification |
|---|---|---|
| REF-AN-01 | Analyse | Texte synthétique mentionnant un débit effectué deux fois : vérifier présence des champs urgence, sentiment, mots-clés, résumé, catégorie/motif et correlation ID ; confirmer les valeurs métier attendues. |
| REF-AN-02 | Analyse courte/invalidité | Texte vide, très court et texte ordinaire : vérifier validation d’entrée et comportement documenté des règles de repli sans appel LLM non nécessaire. |
| REF-KB-01 | Base institutionnelle | Question synthétique dont la réponse existe dans un document institutionnel validé : vérifier source, catégorie et pertinence retournées. |
| REF-KB-02 | Isolation | Recherche dans un projet sans droit à une autre base/collection : vérifier refus ou absence stricte de contenu non autorisé. |
| REF-RAG-01 | Cas similaires | Réclamation synthétique avec catégorie/motif/type connus : vérifier top-k, filtres et métadonnées retournés, sans mélange des tenants. |
| REF-RAG-02 | Aucun résultat | Requête synthétique sans résultat similaire : vérifier réponse explicite sans inventer de cas ou solution source. |
| REF-TR-01 | Transcription | Audio synthétique connu avec nombres, négation et montant : vérifier préservation des faits, segmentation/horodatage si fournis, payload de sortie et suppression du fichier temporaire. |
| REF-TR-02 | Limite/fournisseur | Format non supporté, dépassement de taille et timeout fournisseur : vérifier erreurs explicites, nettoyage du temporaire et absence de contenu sensible dans les logs. |
| REF-REP-01 | Reporting | Question autorisée sur le nombre de dossiers par période et filtre : vérifier métrique, dates, filtre, requête métier et visualisation attendue. |
| REF-REP-02 | Reporting non supporté | Demande hors catalogue ou tentative de champ/opération arbitraire : vérifier refus contrôlé et aucune exécution non autorisée. |
| REF-SYNC-01 | Synchronisation | Page Java contenant insertion, mise à jour, doublon et dossier exclu : vérifier idempotence, compteurs, curseur et exclusion documentée. |
| REF-SYNC-02 | Reprise | Erreur réseau ou réponse paginée invalide : vérifier rollback, état d’erreur persisté, absence de progression erronée du curseur et reprise possible. |
| REF-FB-01 | Feedback/RAG | Dossier validé/corrigé avec solution retenue, dossier sans validation et dossier sans solution : seul le premier groupe admissible doit alimenter l’index selon la règle métier confirmée. |

## 8. Arbitrages à traiter au besoin

La frontière Core/modules est établie : ModulAI est la plateforme unique et modulaire ; le Core AI reste générique ; aucune logique métier GPR ne sera codée en dur dans le Core.

Les décisions détaillées sur les fournisseurs, les données et droits, la compatibilité des routes historiques, l’hébergement des services/modules et le triage des tests GPR ne sont pas des prérequis de cadrage. Elles seront prises uniquement au moment où le service concerné l’exige. Les six tests GPR en échec/erreur sont conservés comme baseline ; ils ne bloquent pas le démarrage des travaux.

## 9. Conclusion

Le cadrage suffisant pour commencer est terminé. ModulAI dispose déjà de fondations génériques de configuration, orchestration, provider et RAG ; les capacités GPR identifiées devront être appelées comme services/modules via les mécanismes génériques de la plateforme, sans ajouter de logique GPR au Core AI.

Aucun service GPR n’a encore été intégré. La suite est l’implémentation du mécanisme générique nécessaire au premier service, avec le périmètre et le contrat minimaux utiles, puis validation de bout en bout.
