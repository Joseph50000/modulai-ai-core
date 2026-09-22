# Plan d'implementation - simplification de la configuration ModulAI

## 1. Objectif

Mettre en place une resolution unique, deterministe et auditable de la configuration IA, sans casser les fonctionnalites existantes :

- authentification et cles API ;
- scopes et autorisations ;
- projets et modules ;
- gateway dynamique ;
- providers et modeles ;
- prompts et policies ;
- RAG et bases de connaissances ;
- logs, audit et documentation API.

Le projet ne doit pas repartir de zero. Le `ConfigurationResolver` existant devient la source officielle de resolution.

## 2. Architecture cible

```text
Application cliente
  -> Backend Gateway
      -> authentification, scopes, projet, endpoint, validation
      -> contrat d'appel minimal
          -> AI Core
              -> ConfigurationResolver
              -> provider, modele, prompt, policy, RAG, limites
              -> execution et snapshot d'audit
  <- reponse structuree
```

Les responsabilites sont reparties sur quatre niveaux :

```text
Plateforme
  -> Projet client
      -> API / Use Case
          -> Execution
```

## 3. Regles de responsabilite

### Plateforme

Definit les providers, les modeles disponibles, les limites maximales, les regles de securite, la configuration technique du RAG et les valeurs par defaut.

### Projet client

Definit les ressources autorisees : modeles, providers, quotas, environnements, bases de connaissances, policies, cles API et scopes.

### API / Use Case

Definit la fonctionnalite : endpoint, prompt actif, version du prompt, schemas d'entree et de sortie, activation du RAG et regles specifiques.

### Execution

Fournit les donnees temporaires : entree, variables, requete RAG et options ponctuelles autorisees. Elle conserve le resultat, le statut et l'audit.

### Etat d'avancement global

#### Phase 0 - cadrage et cartographie

**Statut : TERMINEE.**

La cartographie initiale du Core, du gateway, du frontend et du modele de donnees a ete realisee. Elle a confirme que le `ConfigurationResolver` existe deja, que le gateway reconstruit encore une partie de la configuration et que le contrat historique melange identifiants, donnees d'appel et options de configuration.

#### Phase 1 - contrat canonique Gateway -> AI Core

**Statut : EN COURS - implementation du contrat realisee, validation d'integration restante.**

Le gateway emet maintenant `module_id`, `module_key`, `use_case_key`, `input` et `request_options`. Le Core accepte ces champs et conserve les champs historiques pour assurer une migration sans rupture.

La phase n'est pas encore terminee : il reste a tester un appel reel, definir les erreurs de contrat, confirmer les champs obligatoires et verifier la compatibilite avec les appels frontend.

#### Phase 2 - stabilisation du ConfigurationResolver

**Statut : AMORCEE - adaptation au contrat canonique realisee, stabilisation fonctionnelle restante.**

Le resolver lit deja les identifiants canoniques et les options ponctuelles. Il produit toujours le snapshot de configuration resolue.

La stabilisation complete n'est pas encore realisee : les fallbacks concurrents existent encore dans l'orchestrateur, les priorites doivent etre testees, et les validations strictes du contrat et des options doivent etre formalisees.

#### Prochaine etape

Terminer la validation de la phase 1, puis ajouter les tests de resolution de la phase 2 avant de supprimer les chemins legacy.

## 4. Phase 0 - cadrage et cartographie

### Objectif

Connaitre le comportement reel du code avant de modifier l'architecture.

### Actions

1. Confirmer la branche active et l'etat de chaque depot.
2. Cartographier les fichiers qui resolvent ou reconstruisent :
   - le provider ;
   - le modele ;
   - le prompt ;
   - la policy ;
   - le RAG ;
   - les limites d'execution.
3. Cartographier le flux Backend Gateway -> AI Core.
4. Lister les champs canoniques et les alias legacy.
5. Identifier les parametres affiches par le frontend mais non appliques.
6. Documenter les dependances entre projet, module, use case, prompt, policy et base de connaissances.

### Livrables

- tableau de cartographie des sources de configuration ;
- schema du contrat actuel Gateway -> AI Core ;
- liste des divergences entre documentation et code ;
- liste des champs legacy a conserver temporairement.

### Etat de la cartographie initiale

La cartographie du code confirme les premiers points suivants :

| Zone | Emplacement | Constat |
|---|---|---|
| Resolver officiel | `ai-core-fastapi/src/config_resolver.py` | Resout deja settings, projet, module, provider, modele, prompt, policy, version Core et RAG. Produit un snapshot. |
| Orchestration Core | `ai-core-fastapi/src/orchestrator.py` | Utilise le resolver, mais conserve encore `_fetch_prompt_config()` comme fallback concurrent. Les anciens fetchers provider, modele et policy existent encore. |
| Gateway dynamique | `backend-node/src/routes/gateway.js` | Identifie le module et le use case, mais reconstruit encore `modelOptions`, `ragConfig` et `outputSchema` avant l'appel au Core. |
| Contrat historique observe en phase 0 | `backend-node/src/routes/gateway.js` | Melange `module`, `use_case`, `user_prompt`, `variables`, `output_schema`, `model_options`, `rag_config`, `project_id` et des references d'entree/contexte. La phase 1 ajoute maintenant le contrat canonique en parallele. |
| Frontend Core | `frontend/src/core/ai/coreConfig.js` | Expose des valeurs par defaut (`default_provider`, `default_model_id`, temperature, token limit et strategie RAG) ; leur application reelle doit etre verifiee cote API. |
| Modele de donnees | `backend-node/prisma/schema.prisma` | Les configurations sont majoritairement stockees dans des champs JSON/String (`Project.configuration`, `Module.configuration`, `Module.use_cases`, `Module.endpoints`). |

Cette cartographie confirme que le premier changement fonctionnel doit etre realise dans le Core et le contrat Gateway -> AI Core, avant toute migration du schema ou refonte frontend.

### Critere de sortie

Chaque parametre de configuration possede une source, une priorite et un consommateur identifie.

## 5. Phase 1 - contrat canonique Gateway -> AI Core

### Etat d'avancement

**Statut : EN COURS - implementation compatible realisee, validation fonctionnelle restante.**

#### Realise

- Les identifiants canoniques `module_id`, `module_key` et `use_case_key` sont definis.
- `input` separe les donnees d'appel de la configuration.
- `request_options` porte les options ponctuelles autorisees.
- Le gateway emet le contrat canonique.
- Le `ConfigurationResolver` accepte le nouveau contrat.
- L'orchestrateur Core utilise `input` et `use_case_key`.
- Les champs legacy sont conserves pour eviter une rupture.
- La syntaxe Python et JavaScript a ete verifiee.
- Les erreurs de format ont ete verifiees avec `git diff --check`.

#### Reste a faire

- Ajouter les tests automatises du contrat Gateway -> AI Core.
- Tester un appel reel avec le nouveau payload.
- Verifier les erreurs de contrat et les champs obligatoires.
- Definir les options ponctuelles effectivement autorisees par les policies.
- Confirmer la compatibilite avec les appels frontend existants.
- Passer la phase 1 a `TERMINEE` apres validation d'integration.

#### Prochaine action

Ajouter et executer les tests du contrat canonique avant de commencer la suppression des reconstructions legacy du gateway en phase 2.

### Objectif

Definir un contrat minimal qui transmet l'identite de l'appel et les donnees, sans reconstruire la configuration permanente dans le gateway.

### Contrat cible indicatif

```json
{
  "project_id": "project_123",
  "module_id": "module_123",
  "use_case_key": "analyse-plainte",
  "input": {},
  "request_options": {}
}
```

### Actions

1. Definir les noms canoniques des identifiants.
2. Definir les options ponctuelles autorisees.
3. Definir les champs refuses ou ignores.
4. Definir les erreurs de contrat et de validation.
5. Versionner le contrat si une incompatibilite est necessaire.

### Critere de sortie

Le contrat est documente et peut etre utilise par le gateway, le Core et les tests d'integration.

### Implementation initiale realisee

Le contrat canonique est maintenant emis par `backend-node/src/routes/gateway.js` avec :

- `module_id` ;
- `module_key` ;
- `use_case_key` ;
- `input` ;
- `request_options`.

Les champs historiques (`module`, `use_case`, `variables`, `model_options`, `rag_config` et `output_schema`) sont encore transmis afin de preserver la compatibilite pendant la migration.

Le Core accepte ces nouveaux champs dans `ai-core-fastapi/src/config_resolver.py` et `ai-core-fastapi/src/orchestrator.py`. Les options `rag_query` et `top_k` sont separees dans `request_options`, tandis que la resolution legacy reste disponible temporairement.

## 6. Phase 2 - stabilisation du ConfigurationResolver

### Etat d'avancement

**Statut : AMORCEE - support du contrat canonique integre, tests et durcissement restants.**

#### Realise

- Le resolver lit `module_key` et `use_case_key`.
- Les options `request_options` sont prises en compte avec compatibilite legacy.
- Le snapshot contient l'identifiant `use_case_key`.
- Les champs legacy restent acceptes pendant la migration.

#### Reste a faire

- Tester l'ordre de priorite entre policy, API/use case, projet, modele et defaults plateforme.
- Formaliser les champs obligatoires et les erreurs de configuration.
- Encadrer les options ponctuelles autorisees.
- Supprimer les resolutions concurrentes de prompt, provider, modele et policy dans l'orchestrateur.
- Confirmer la stabilite du snapshot dans les cas nominaux et les cas d'erreur.

#### Prochaine action

Ajouter les tests du resolver et comparer les resultats du contrat canonique avec ceux du format legacy avant toute suppression de fallback.

### Objectif

Faire du resolver du Core l'unique source de resolution.

### Actions

1. Formaliser l'ordre de priorite :

   ```text
   Policy de securite
     -> API / Use Case
     -> Projet
     -> Modele
     -> Defaults plateforme
   ```

2. Normaliser les identifiants et les aliases d'entree.
3. Valider les providers et modeles autorises.
4. Verifier l'existence d'un prompt actif et versionne.
5. Verifier les droits d'acces aux Knowledge Bases.
6. Appliquer les limites maximales et les policies.
7. Produire un snapshot de configuration resolue.
8. Distinguer explicitement le format canonique du format legacy.

### Snapshot minimal attendu

```json
{
  "project_id": "project_123",
  "module_id": "module_123",
  "use_case": "analyse-plainte",
  "provider_id": "provider_123",
  "model_id": "model_123",
  "prompt_id": "prompt_123",
  "prompt_version": "1.0.0",
  "policy_id": "policy_123",
  "temperature": 0.3,
  "token_limit": 1024,
  "rag": {
    "enabled": true,
    "knowledge_base_id": "kb_123",
    "collection": "claims",
    "top_k": 3
  },
  "policy_violations": []
}
```

## 7. Phase 3 - tests du resolver

### Tests de resolution

- defaults plateforme ;
- override projet ;
- override API / use case ;
- limites imposees par une policy ;
- fallback de modele ;
- prompt absent ;
- prompt actif et version ;
- RAG active ;
- RAG interdit ;
- Knowledge Base hors perimetre ;
- configuration invalide ;
- snapshot complet et stable.

### Critere de sortie

Les regles de priorite sont testees avant la suppression des chemins concurrents.

## 8. Phase 4 - suppression des doubles resolutions dans le Core

### Objectif

Utiliser le resultat du resolver dans tout le chemin d'execution.

### Actions

1. Modifier `orchestrator.py` pour consommer la configuration resolue.
2. Supprimer les resolutions concurrentes de provider.
3. Supprimer les resolutions concurrentes de modele.
4. Supprimer la recherche parallele de prompt.
5. Supprimer les reconstructions paralleles de policy et de RAG.
6. Conserver temporairement les fallbacks legacy uniquement s'ils sont traces et clairement identifies.
7. Faire remonter les erreurs de configuration au lieu de les remplacer par des valeurs silencieuses.

### Critere de sortie

Une execution standard ne prend ses decisions de configuration qu'a travers le `ConfigurationResolver`.

## 9. Phase 5 - simplification du Backend Gateway

### Objectif

Limiter le gateway a l'acces, au controle et au routage.

### Responsabilites a conserver

- authentification ;
- validation de cle API ;
- scopes ;
- projet et environnement ;
- endpoint publie ;
- validation de la requete ;
- CORS ;
- logs d'appel ;
- routage vers le Core.

### Responsabilites a retirer progressivement

- selection du provider ;
- selection du modele ;
- reconstruction de `modelOptions` ;
- reconstruction de `ragConfig` ;
- reconstruction de `outputSchema` ;
- resolution permanente de la configuration.

### Critere de sortie

Le gateway envoie le contrat canonique et les donnees d'appel ; le Core resout la configuration.

## 10. Phase 6 - migration legacy

### Strategie

```text
Lire l'ancien format
  -> convertir vers le format canonique
  -> journaliser l'utilisation legacy
  -> comparer les resolutions
  -> migrer les donnees
  -> supprimer les anciens chemins
```

### Actions

1. Definir un normaliseur unique des aliases.
2. Produire une resolution canonique pour les anciennes donnees.
3. Comparer ancien et nouveau resultat pendant la transition.
4. Corriger les ecarts documentes.
5. Migrer les donnees persistantes.
6. Ajouter des avertissements sur les champs deprecies.
7. Supprimer les aliases uniquement apres verification des usages.

## 11. Phase 7 - simplification du frontend

### Objectif

Aligner l'interface sur les valeurs effectivement appliquees.

### Actions

1. Afficher distinctement :
   - valeur heritee ;
   - valeur configuree ;
   - valeur finale appliquee.
2. Retirer les parametres que le backend ou le Core n'appliquent pas.
3. Adapter les formulaires de configuration Core, projet, module et policy.
4. Afficher le prompt actif et sa version.
5. Afficher les restrictions RAG et les Knowledge Bases autorisees.
6. Afficher le snapshot ou un resume de la configuration resolue lorsque cela est utile.

### Critere de sortie

Chaque valeur modifiable dans l'interface a un effet reel, trace et verifiable.

## 12. Phase 8 - preservation des fonctionnalites existantes

Verifier a chaque phase que la simplification ne casse pas :

- les cles API ;
- les scopes ;
- le CORS par projet ;
- les logs API ;
- la documentation OpenAPI ;
- l'upload de documents ;
- les collections Chroma ;
- la pagination RAG ;
- l'inspection des bases de connaissances ;
- les reponses structurees.

## 13. Phase 9 - validation bout en bout

Executer le parcours suivant :

```text
Creer un provider
  -> creer un modele
  -> creer un module
  -> creer un use case
  -> publier un prompt
  -> creer un projet client
  -> autoriser une Knowledge Base
  -> creer une cle API
  -> appeler l'endpoint
  -> authentifier et autoriser
  -> resoudre la configuration
  -> executer le Core
  -> utiliser le RAG si autorise
  -> enregistrer l'audit
  -> retourner une reponse structuree
```

### Cas d'erreur a valider

- cle API invalide ou expiree ;
- scope manquant ;
- projet inactif ;
- endpoint non publie ;
- module non publie ;
- donnees invalides ;
- provider indisponible ;
- modele non autorise ;
- prompt absent ;
- RAG interdit ;
- Knowledge Base non autorisee.

## 14. Ordre d'implementation recommande

```text
1. Cartographier l'existant
2. Definir le contrat canonique
3. Tester et stabiliser le ConfigurationResolver
4. Supprimer les doubles resolutions du Core
5. Simplifier le Backend Gateway
6. Migrer les formats legacy
7. Adapter le frontend
8. Nettoyer progressivement le modele de donnees
9. Executer les tests bout en bout
```

Ne pas commencer par :

- un grand nettoyage de base de donnees ;
- une refonte complete du frontend ;
- la suppression immediate des champs legacy ;
- une nouvelle architecture parallele.

## 15. Definition de fini

Le chantier est considere comme termine lorsque :

- le Core possede une seule source officielle de resolution ;
- le gateway ne reconstruit plus la configuration IA ;
- les priorites sont documentees et testees ;
- chaque execution produit un snapshot auditable ;
- les anciens formats sont migres ou explicitement deprecies ;
- les valeurs affichees par le frontend sont effectivement appliquees ;
- les fonctions API et RAG existantes sont preservees ;
- le parcours bout en bout reussit ;
- les erreurs de configuration sont explicites et observables.
