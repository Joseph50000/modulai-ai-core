# Analyse réalignée de la simplification ModulAI

## 1. Contexte

La branche de travail a été réalignée sur la branche distante la plus récente :

```text
origin/fix/env-and-db-bootstrap
```

La branche locale de travail est :

```text
refactor/simplify-ai-configuration
```

Elle existe dans les trois services :

- `modulai-frontend`
- `modulai-backend-node`
- `modulai-ai-core`

Les trois dépôts sont actuellement alignés avec `origin/fix/env-and-db-bootstrap`.

## 2. Conclusion principale

La branche `fix/env-and-db-bootstrap` contient déjà une partie importante de l'architecture nécessaire à la simplification.

Il ne faut donc pas repartir de zéro ni créer une deuxième architecture de configuration.

Le travail doit être une consolidation de l'existant :

```text
Conserver le resolver existant
  → supprimer les résolutions concurrentes
  → réduire les configurations répétées
  → normaliser le contrat API
  → simplifier le frontend
  → migrer progressivement les champs legacy
```

## 3. Éléments déjà présents

### AI Core

Le fichier :

```text
modulai-ai-core/src/config_resolver.py
```

contient déjà un `ConfigurationResolver` qui :

- charge les paramètres Core ;
- charge la configuration projet ;
- charge la configuration module ;
- sélectionne un provider ;
- sélectionne un modèle ;
- sélectionne un prompt ;
- sélectionne une policy ;
- sélectionne une version du Core ;
- résout la configuration RAG ;
- vérifie l'accès aux Knowledge Bases ;
- applique certaines limites ;
- produit un snapshot auditable.

### Backend

Le backend contient déjà :

- le gateway dynamique ;
- le routage des endpoints publiés ;
- les logs API ;
- le middleware CORS par projet ;
- les routes RAG ;
- la prise en charge des projets et des modules ;
- le proxy vers l'AI Core.

Fichiers importants :

```text
modulai-backend-node/src/routes/gateway.js
modulai-backend-node/src/middleware/projectCors.js
modulai-backend-node/src/routes/rag.js
```

### Frontend

Le frontend contient déjà :

- la gestion des clés API ;
- la documentation API ;
- les scopes ;
- les logs d'utilisation ;
- le test des endpoints ;
- la configuration CORS par projet ;
- la gestion des Knowledge Bases ;
- l'exploration Chroma ;
- la gestion des providers, modèles, prompts et policies.

## 4. Problèmes constatés après réalignement

## 4.1 Deux systèmes de résolution coexistent

Le nouveau resolver existe déjà, mais `orchestrator.py` conserve encore des méthodes historiques :

```text
_fetch_active_provider()
_fetch_default_model()
_fetch_active_policy()
_fetch_prompt_config()
```

Le Core possède donc encore :

```text
nouveau ConfigurationResolver
+
anciens fallbacks directs
```

Cela crée un risque de comportement différent selon le chemin d'exécution.

## 4.2 Le gateway reconstruit encore la configuration

Dans `gateway.js`, le backend construit encore une partie de :

```text
modelOptions
ragConfig
outputSchema
```

à partir de `module.configuration` et des données du use case.

Cette responsabilité chevauche celle du `ConfigurationResolver`.

Le gateway devrait principalement gérer :

- l'authentification ;
- la clé API ;
- les scopes ;
- le projet ;
- l'endpoint ;
- la validation de la requête ;
- le routage vers l'AI Core.

## 4.3 Plusieurs noms représentent la même configuration

Le resolver accepte encore différents noms pour un même concept :

```text
model
model_id
default_model_id

provider
provider_id
default_provider

knowledge_base_id
knowledge_base_collection
collection
```

Cette compatibilité est utile pendant une migration, mais elle ne doit pas devenir le modèle définitif.

## 4.4 Le projet et le module se chevauchent

Les overrides peuvent encore exister dans :

- CoreSettings ;
- configuration projet ;
- configuration module ;
- use case ;
- policy ;
- payload d'exécution.

La hiérarchie existe, mais elle est trop permissive.

## 4.5 Les prompts ont plusieurs points d'entrée

Les prompts peuvent être retrouvés par :

- `prompt_id` ;
- `module_id` ;
- `project_id` ;
- `name` ;
- `use_case` ;
- clé composite module/use case.

Cela rend la sélection moins prévisible.

## 4.6 Le RAG est configuré à plusieurs niveaux

Le RAG est actuellement présent dans :

```text
Core global
Projet
Module
Use Case
Policy
Payload
```

Il faut conserver ces niveaux uniquement lorsqu'ils ont des responsabilités différentes.

## 4.7 Certaines valeurs sont exposées mais partiellement appliquées

L'interface expose plusieurs paramètres qui ne sont pas tous appliqués de façon uniforme :

```text
default_provider
default_temperature
default_token_limit
default_rag_strategy
default_validation_policy
max_execution_time
allowed_models
fallback_model_id
```

Le système doit soit les appliquer réellement, soit les retirer de l'interface.

## 5. Modèle cible

La configuration cible doit être organisée autour de quatre niveaux :

```text
Plateforme
  → Projet client
      → API / Use Case
          → Exécution
```

### 5.1 Plateforme

Responsabilité : infrastructure, disponibilité et sécurité.

Contient :

- providers ;
- modèles disponibles ;
- version du Core ;
- limites maximales ;
- règles de sécurité ;
- configuration technique du RAG ;
- valeurs par défaut.

### 5.2 Projet client

Responsabilité : ce que l'organisation cliente est autorisée à utiliser.

Contient :

- provider autorisé ;
- modèle par défaut ;
- quotas ;
- environnements ;
- bases de connaissances autorisées ;
- policies du projet ;
- clés API ;
- scopes.

### 5.3 API / Use Case

Responsabilité : ce que fait une API.

Contient :

- endpoint ;
- nom du use case ;
- prompt actif ;
- version du prompt ;
- schéma d'entrée ;
- schéma de sortie ;
- activation du RAG ;
- policy spécifique si nécessaire.

### 5.4 Exécution

Responsabilité : données temporaires et contexte d'un appel.

Contient :

- données d'entrée ;
- variables ;
- requête RAG ;
- options ponctuelles autorisées ;
- configuration finale résolue ;
- résultat ;
- statut ;
- audit.

## 6. Hiérarchie de résolution recommandée

La résolution doit être déterministe et documentée :

```text
Policy de sécurité
  → configuration API / Use Case
  → configuration projet
  → configuration modèle
  → defaults plateforme
```

Une valeur ne doit être surchargeable que si son niveau a explicitement le droit de le faire.

Exemple :

```text
La plateforme peut imposer temperature_max = 0.7.
Un projet peut choisir temperature = 0.3.
Une API peut demander temperature = 0.5.
La valeur finale ne peut jamais dépasser 0.7.
```

## 7. Configuration résolue attendue

Chaque exécution doit produire un snapshot similaire à :

```json
{
  "project_id": "project_123",
  "module_id": "module_123",
  "use_case": "analyse-plainte",
  "provider_id": "provider_123",
  "model_id": "model_123",
  "model_key": "llama3.2:1b",
  "prompt_id": "prompt_123",
  "prompt_version": "1.0.0",
  "policy_id": "policy_123",
  "core_version": "1.0.0",
  "temperature": 0.3,
  "token_limit": 1024,
  "rag": {
    "enabled": true,
    "knowledge_base_id": "kb_123",
    "collection": "claims",
    "top_k": 3
  },
  "human_validation_required": true,
  "policy_violations": []
}
```

Ce snapshot permet de savoir exactement comment chaque réponse a été produite.

## 8. Plan d'implémentation réaligné

### Phase 1 — Cartographier l'existant

Documenter pour chaque paramètre :

- où il est stocké ;
- où il est modifié ;
- où il est lu ;
- qui a priorité ;
- s'il est réellement utilisé.

Ne pas supprimer de champ avant cette cartographie.

### Phase 2 — Stabiliser le ConfigurationResolver

Conserver :

```text
modulai-ai-core/src/config_resolver.py
```

comme point de résolution officiel.

Ajouter ou clarifier :

- les identifiants canoniques ;
- les priorités ;
- les validations ;
- les erreurs de configuration ;
- la distinction entre migration legacy et nouveau format.

### Phase 3 — Normaliser le contrat Gateway → AI Core

Le gateway doit transmettre des identifiants et les données d'appel :

```json
{
  "project_id": "project_123",
  "module_id": "module_123",
  "use_case_key": "analyse-plainte",
  "input": {},
  "request_options": {}
}
```

Il ne doit plus reconstruire toute la configuration permanente du Core.

### Phase 4 — Supprimer les doubles résolutions

Dans `orchestrator.py` :

- supprimer les appels concurrents de récupération des providers ;
- supprimer les appels concurrents de récupération des modèles ;
- supprimer la recherche de prompt parallèle ;
- utiliser le résultat du resolver ;
- conserver uniquement les contrôles d'exécution et de sécurité.

Les fallbacks historiques doivent être temporaires et explicitement marqués comme legacy.

### Phase 5 — Unifier les prompts

La source de vérité doit devenir :

```text
Use Case
  → prompt_id
  → version active
```

Le système doit :

- garantir une version active ;
- refuser une API sans prompt actif ;
- tracer `prompt_id` et `prompt_version` ;
- déprécier les recherches ambiguës par nom.

### Phase 6 — Unifier le RAG

Responsabilités finales :

```text
Plateforme :
  embeddings et moteur vectoriel

Projet :
  bases autorisées

API / Use Case :
  RAG activé ou non

Policy :
  RAG obligatoire ou interdit

Exécution :
  requête et top_k
```

### Phase 7 — Simplifier le frontend

Les écrans doivent clairement distinguer :

```text
Valeur héritée
Valeur configurée
Valeur finale appliquée
```

Le frontend ne doit plus proposer de paramètres qui ne sont pas appliqués par le backend ou l'AI Core.

Les écrans concernés incluent :

- `CoreSettingsForm.jsx` ;
- `ProjectCoreConfig.jsx` ;
- `ModuleConfigurationManager.jsx` ;
- `PoliciesManager.jsx` ;
- `CorePromptsManager.jsx` ;
- `ModulePromptsManager.jsx`.

### Phase 8 — Nettoyer le modèle de données

Après migration :

- garder un identifiant unique pour un modèle ;
- garder une URL canonique par provider ;
- éviter les noms dénormalisés ;
- formaliser les relations projet/API/use case/prompt ;
- déprécier les champs legacy ;
- conserver le snapshot d'exécution.

### Phase 9 — Préserver les fonctionnalités API/RAG existantes

Les fonctionnalités déjà présentes sur la branche doivent rester indépendantes de la simplification :

- CORS par projet ;
- clés API ;
- scopes ;
- logs API ;
- documentation OpenAPI ;
- upload de documents ;
- collections Chroma ;
- pagination RAG ;
- inspection des bases de connaissances.

La simplification ne doit pas réintroduire les problèmes corrigés dans `fix/env-and-db-bootstrap`.

### Phase 10 — Migrer progressivement

Procédure recommandée :

1. ajouter le nouveau format ;
2. lire l'ancien format en compatibilité ;
3. produire un snapshot avec les deux résolutions ;
4. comparer les résultats ;
5. corriger les écarts ;
6. basculer les nouvelles APIs ;
7. migrer les données ;
8. supprimer les chemins legacy.

## 9. Tests nécessaires

### Tests de résolution

Tester :

- defaults plateforme ;
- override projet ;
- override API ;
- policy globale ;
- policy projet ;
- policy module ;
- policy use case ;
- fallback modèle ;
- RAG autorisé ;
- RAG interdit ;
- Knowledge Base hors périmètre.

### Tests API

Tester :

- clé API invalide ;
- scope manquant ;
- projet inactif ;
- endpoint non publié ;
- données invalides ;
- CORS autorisé ;
- CORS refusé ;
- logs API ;
- réponse structurée.

### Test de bout en bout

```text
Créer provider
  → créer modèle
  → créer module
  → créer use case
  → publier prompt
  → créer projet client
  → autoriser une base de connaissances
  → créer une clé API
  → appeler l'endpoint
  → résoudre la configuration
  → exécuter le Core
  → enregistrer l'audit
  → retourner la réponse
```

## 10. Décision finale

La branche actuelle contient déjà les fondations de la simplification.

La priorité n'est pas de créer davantage de configuration, mais de :

1. choisir une seule source de résolution ;
2. supprimer les chemins concurrents ;
3. réduire les paramètres modifiables ;
4. clarifier les responsabilités des niveaux ;
5. rendre la configuration finale visible et auditable ;
6. préserver les fonctionnalités API et RAG déjà ajoutées.

Le résultat attendu est :

```text
La plateforme définit ce qui est autorisé.
Le projet client définit ce qu'il peut utiliser.
L'API définit ce qu'elle fait.
L'exécution fournit les données.
Le Core résout une configuration unique.
L'application cliente reçoit une réponse structurée.
```
