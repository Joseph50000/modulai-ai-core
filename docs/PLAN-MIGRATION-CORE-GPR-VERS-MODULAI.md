# Plan d’implémentation — migration du Core GPR vers ModulAI

## 1. Objectif

Intégrer progressivement les capacités métier du dépôt source `gpr_ai_service` dans la plateforme modulaire ModulAI, comme services/modules configurables pour différents projets. Le Core AI ModulAI reste générique et ne contient ni code métier GPR, ni imports, règles, prompts, catégories ou configurations GPR en dur. Les capacités GPR sont des services de module invoqués via des contrats et interfaces génériques du Core.

Le dépôt GPR existant sert de référence fonctionnelle pour les services/modules à intégrer dans ModulAI. Son code ne doit pas être copié en bloc : chaque capacité sera adaptée aux contrats, à la résolution de configuration, à la sécurité et à l’observabilité de ModulAI. La topologie d’hébergement des services de module reste à décider ; dans tous les cas, le Core ne doit pas dépendre directement du code GPR.

## 2. État du plan

**Statut : Phase 0 terminée ; implémentation fonctionnelle non démarrée.**

Le cadrage minimal est terminé : les capacités GPR et les fondations réutilisables de ModulAI sont identifiées. ModulAI possède déjà un contrat canonique Gateway → AI Core et un `ConfigurationResolver`. La suite consiste à implémenter le mécanisme générique strictement nécessaire pour appeler un service/module sans ajouter de logique GPR au Core. Les décisions propres à chaque capacité seront prises au moment où elles deviennent nécessaires, pas comme une longue phase préalable.

## 3. Architecture cible

```text
Client ou interface ModulAI
  -> Backend Gateway ModulAI
      -> authentification, autorisation et validation
      -> contrat canonique d’exécution
          -> AI Core ModulAI
              -> ConfigurationResolver
              -> résolution générique du module/service activé
              -> interface d’exécution de module
                  -> services du module GPR (hors code métier du Core)
                  -> accès autorisés aux sources de données nécessaires
              -> réponse structurée et trace d’audit
```

### Responsabilités

- **Core ModulAI** : contrat d’exécution, résolution de configuration, orchestration, politiques, fournisseurs IA, validation des entrées/sorties et traçabilité.
- **Services/modules GPR** : capacités métier, use cases, schémas, configurations et règles GPR, enregistrés/configurés dans ModulAI comme modules — jamais codés en dur dans le Core AI.
- **Interface générique d’exécution** : contrat permettant au Core de résoudre et d’appeler les services/modules sans importer ni connaître leur logique spécifique.
- **Accès aux données GPR** : connecteurs utilisés par les services/modules selon le besoin. Ils ne rendent pas le Core dépendant des détails Java/MySQL.
- **Gateway** : identité de l’appelant, autorisations par projet/module/cas d’usage, limites et routage.

Le contrat canonique existant (`module_key`, `use_case_key`, `input`, `request_options`) constitue le point d’entrée des modules. Les options ponctuelles restent limitées par la configuration et les permissions du projet.

## 4. Modules et périmètre fonctionnel

| Capacité | Cible de migration | Dépendance ou précaution |
|---|---|---|
| Analyse de réclamation | Module d’analyse : sentiment, urgence, mots-clés sensibles, classification et résumé | Distinguer les composants NLP réutilisables des règles métier GPR. |
| Connaissance institutionnelle | Module de connaissance et recherche RAG | Contrôler les sources et isoler les index et données par projet/tenant. |
| Recherche de réclamations similaires | Module de recherche RAG historique et proposition de solution | Définir ingestion, filtrage, actualisation et autorisations des collections. |
| Synchronisation des données | Adaptateur/connecteur GPR hors du cœur IA | Protéger les déclenchements et gérer pagination, reprise, erreurs et idempotence. |
| Transcription | Module de transcription configurable | Fournisseur interchangeable, limites audio, rétention et traitement des données sensibles. |
| Reporting | Module de reporting, tableau de bord et requêtes en langage naturel | Conserver un catalogue d’analyses autorisées ; ne pas exécuter de SQL arbitraire généré par le LLM. |
| Retours utilisateurs | Alimentation contrôlée du RAG lorsque les retours sont validés | Ne pas assimiler l’enrichissement RAG à l’entraînement ou au fine-tuning du modèle. |

## 5. Phases d’implémentation

### Phase 0 — Cadrage et état de référence

**Objectif :** établir une référence précise avant tout déplacement de code.

Actions :

1. Comparer les capacités, contrats, routes et dépendances du Core GPR et de ModulAI.
2. Identifier les composants déjà présents dans ModulAI afin d’éviter les duplications (resolver, orchestration, providers, RAG, audit).
3. Définir des jeux d’entrées et sorties représentatifs pour l’analyse, la recherche, la transcription et le reporting.
4. Relever les règles métier, sources de données, secrets et exigences de rétention.

**Statut : TERMINÉE.** Cartographie et baseline des tests consignées dans le compte-rendu Phase 0. Les scénarios détaillés seront ajoutés avec les tests du premier service intégré, sans bloquer le démarrage.

### Phase 1 — Stabilisation du socle ModulAI

**Objectif :** rendre le chemin canonique Gateway → Core fiable avant l’ajout de modules métier.

Actions :

1. Compléter les tests de contrat et de résolution de configuration.
2. Clarifier les priorités du `ConfigurationResolver`, les options d’exécution autorisées et les erreurs de contrat.
3. Vérifier les appels existants de bout en bout et leur compatibilité.
4. Retirer les résolutions concurrentes et champs legacy uniquement après validation et période de compatibilité appropriée.

**Critère de sortie :** un appel canonique résout une configuration déterministe et testée ; le retrait des chemins legacy est couvert par des tests.

### Phase 2 — Sécurité et autorisations

**Objectif :** établir les contrôles d’accès avant d’exposer les capacités métier migrées.

Actions :

1. Définir l’authentification service-à-service et la gestion/rotation des secrets.
2. Appliquer l’autorisation au niveau projet, module, cas d’usage et source de données.
3. Valider les entrées, les sorties, les fichiers, les quotas et les limites de taille/durée.
4. Protéger les opérations d’indexation et de synchronisation par des permissions dédiées.
5. Limiter les données sensibles dans les logs et définir leur rétention.
6. Tester les refus d’accès et tracer les événements de sécurité.

**Critère de sortie :** chaque route ou exécution métier est protégée par une identité et une autorisation côté serveur ; CORS et réseau privé ne sont pas considérés comme substituts.

### Phase 3 — Contrat et cycle de vie des modules

**Objectif :** formaliser comment ModulAI déclare, configure et exécute un module.

Actions :

1. Définir métadonnées, versions, cas d’usage, schémas d’entrée/sortie et dépendances.
2. Définir activation, configuration par projet, politiques et permissions.
3. Intégrer la validation du contrat au routage canonique.
4. Formaliser la réponse, les erreurs et le snapshot d’audit.

**Critère de sortie :** un module peut être activé/configuré par projet et exécuté par son `module_key` et son `use_case_key`, avec entrée/sortie validées.

### Phase 4 — Module pilote : analyse GPR

**Objectif :** valider le modèle de modularité avec une capacité métier représentative.

Actions :

1. Extraire classification, urgence, sentiment, mots-clés et résumé derrière un cas d’usage.
2. Isoler vocabulaire, catégories et règles spécifiques à GPR dans la configuration ou l’extension GPR.
3. Maintenir temporairement les anciennes routes comme façades vers le nouveau module.
4. Comparer les réponses au service de référence et documenter les écarts.

**Critère de sortie :** tests unitaires, contrats, sécurité et appels API de bout en bout passent ; la parité fonctionnelle est acceptée.

### Phase 5 — Connaissance et recherche

**Objectif :** migrer les deux usages RAG en maîtrisant les périmètres de données.

Actions :

1. Migrer la recherche dans les documents institutionnels.
2. Migrer la recherche de réclamations similaires et la génération de propositions.
3. Séparer les collections et appliquer les permissions aux sources, indexations et résultats.
4. Définir les procédures de synchronisation, suppression et réindexation.

**Critère de sortie :** des tests démontrent qu’un projet ne peut ni indexer ni consulter des données hors de son périmètre.

### Phase 6 — Adaptateur et synchronisation GPR

**Objectif :** isoler l’intégration Java/MySQL du Core IA.

Actions :

1. Encapsuler les appels à l’API Java et les opérations SQL dans un adaptateur GPR.
2. Sécuriser et autoriser explicitement les synchronisations manuelles et planifiées.
3. Préserver pagination, curseurs, idempotence, reprise et rapport d’erreurs.
4. Éviter que les identifiants de base ou les détails du schéma GPR soient nécessaires au cœur ModulAI.

**Critère de sortie :** les services/modules GPR accèdent aux sources nécessaires via leurs connecteurs ; l’orchestration générique ModulAI ne dépend ni du code métier GPR ni du schéma Java/MySQL. Les connecteurs sont testés en succès, erreur et reprise.

### Phase 7 — Module de transcription

**Objectif :** rendre la transcription accessible via le contrat modulaire.

Actions :

1. Adapter le pipeline audio au schéma du module et rendre le fournisseur interchangeable.
2. Conserver les contrôles de format, taille, durée et délais d’attente.
3. Encadrer prétraitement, correction, diarisation et structuration comme étapes configurables.
4. Définir suppression des fichiers temporaires, rétention et règles de journalisation.

**Critère de sortie :** les chemins audio et texte, erreurs fournisseur, limites et suppression des fichiers sont vérifiés par tests.

### Phase 8 — Module de reporting

**Objectif :** intégrer tableaux de bord et requêtes en langage naturel dans le système de modules.

Actions :

1. Isoler le catalogue analytique, les filtres et les règles métier GPR.
2. Faire interpréter la question par le modèle, puis valider l’intention contre le catalogue avant toute requête.
3. Appliquer les permissions et filtres de données à chaque exécution.
4. Valider les résultats, visualisations, comparaisons et demandes non prises en charge.

**Critère de sortie :** les requêtes sont bornées au catalogue autorisé, les accès sont filtrés par permissions et les cas invalides échouent explicitement.

### Phase 9 — Déploiement progressif et retrait

**Objectif :** remplacer l’ancien service sans perte de comportement ni rupture imprévue.

Actions :

1. Déployer par capacité et comparer les résultats avec la référence.
2. Suivre erreurs, latence, coûts, usage des modèles et événements d’accès.
3. Préparer le retour arrière et conserver temporairement les façades de compatibilité.
4. Retirer les anciennes routes et implémentations uniquement après validation des consommateurs.
5. Mettre à jour la documentation, les procédures d’exploitation et les configurations.

**Critère de sortie :** parité et stabilité démontrées, retour arrière documenté, anciennes routes retirées après accord de leurs consommateurs.

## 6. Stratégie de validation

Chaque module suit le même parcours de validation :

1. Tests unitaires des règles métier et services.
2. Tests de schémas d’entrée/sortie et de contrat canonique.
3. Tests d’autorisation, isolation des données et limites.
4. Tests d’intégration avec fournisseurs et connecteurs simulés ou contrôlés.
5. Appel de bout en bout sur l’environnement cible.
6. Comparaison avec les réponses de référence du service GPR.

Les tests doivent couvrir les erreurs explicites : configuration absente, permission refusée, source indisponible, fournisseur en erreur, entrée invalide et demande de reporting hors catalogue.

## 7. Principes et critères de décision

- Migrer des capacités, pas le dépôt entier ni ses routes sans adaptation.
- Garder les dépendances GPR dans l’extension et les adaptateurs GPR.
- Réutiliser les services génériques ModulAI lorsqu’ils répondent déjà au besoin.
- Ne pas retirer le comportement historique avant tests de parité et validation des consommateurs.
- Ne pas laisser un LLM accéder directement à des requêtes ou actions non bornées.
- Traiter journaux, audio, transcriptions, réclamations et résultats de reporting comme des données potentiellement sensibles.
- Distinguer enrichissement RAG, collecte de feedback et entraînement d’un modèle.

## 8. Prochaine étape

Terminer la stabilisation du contrat canonique et du `ConfigurationResolver`, puis établir les exigences de sécurité et le jeu de référence du module d’analyse GPR. Aucune migration fonctionnelle ne devrait être exposée avant la mise en place des contrôles d’accès serveur.
