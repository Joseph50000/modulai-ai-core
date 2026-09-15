# Workflow complet de la plateforme ModulAI

## 1. Objectif

ModulAI est une plateforme **AI-as-a-Service**. Elle expose un Core AI sous forme d'APIs afin que des projets externes, des entreprises ou des organisations puissent intégrer des capacités d'intelligence artificielle dans leurs propres applications.

```text
Application d'une organisation
  → API ModulAI
  → module IA configuré
  → modèle d'intelligence artificielle
  → réponse structurée
  → application de l'organisation
```

ModulAI n'est donc pas uniquement une application utilisée directement par un utilisateur. Son rôle principal est de fournir des services IA réutilisables à plusieurs organisations.

Exemple :

```text
Organisation : Entreprise A
Application : outil de gestion des plaintes
API : POST /api/dynamic/gpr/analyse-plainte
Résultat : analyse structurée affichée dans l'outil de l'entreprise
```

## 2. Les rôles

### Administrateur ModulAI

Il opère la plateforme centrale :

- configure les fournisseurs IA ;
- ajoute les modèles ;
- définit les règles de sécurité ;
- publie les modules et leurs APIs ;
- surveille les exécutions et les erreurs.

### Administrateur de l'organisation cliente

Il prépare l'utilisation de ModulAI pour son organisation :

- crée un projet ;
- sélectionne les modules et APIs ;
- configure les tâches métier ;
- ajoute les documents utiles ;
- crée les clés API ;
- définit les droits et les environnements ;
- valide l'intégration avant sa mise en production.

### Équipe technique de l'organisation cliente

Elle intègre ModulAI dans l'application externe :

- conserve la clé API côté serveur ;
- appelle les endpoints publiés ;
- envoie les données au format attendu ;
- traite les réponses et les erreurs ;
- affiche le résultat dans l'application cliente.

### Utilisateur métier de l'organisation cliente

Il utilise l'application de son organisation. Il n'a généralement pas besoin de connaître l'URL de l'API, la clé API ou le modèle utilisé.

```text
Utilisateur métier
  → application de son organisation
  → API ModulAI
  → résultat affiché dans l'application
```

## 3. Vue globale

```text
Administrateur ModulAI
  → configure le Core AI
  → configure les modèles et les règles
  → publie les modules et les APIs

Administrateur organisation cliente
  → crée un projet
  → sélectionne les APIs
  → crée une clé API
  → prépare les données et les droits

Équipe technique cliente
  → intègre l'API dans une application externe
  → teste l'appel
  → traite la réponse

Utilisateur métier
  → utilise l'application externe
  → demande une analyse
  → consulte et vérifie le résultat
```

## 4. Parcours de l'administrateur ModulAI

### Étape 1 : configurer un fournisseur IA

L'administrateur ajoute un fournisseur, par exemple Ollama ou un autre service compatible.

Il renseigne :

- le nom ;
- l'adresse du service ;
- la clé ou le secret si nécessaire ;
- le statut ;
- éventuellement le fournisseur par défaut.

**Résultat attendu :** le fournisseur est disponible et son test de connexion réussit.

**Si le test échoue :** aucun projet ne doit dépendre de ce fournisseur avant correction de l'adresse, de la clé ou du service.

### Étape 2 : ajouter les modèles

L'administrateur enregistre les modèles disponibles auprès des fournisseurs.

Il définit notamment :

- le nom du modèle ;
- ses capacités ;
- sa limite de tokens ;
- sa température par défaut ;
- son statut.

**Résultat attendu :** un projet peut sélectionner un modèle autorisé.

### Étape 3 : définir les règles générales

L'administrateur configure les règles communes :

- modèles autorisés ;
- température maximale ;
- nombre maximal de tokens ;
- durée maximale d'une exécution ;
- obligation de validation humaine ;
- obligation d'utiliser une base documentaire ;
- règles de conservation et d'audit.

**Résultat attendu :** toutes les organisations utilisent l'IA dans un cadre contrôlé.

### Étape 4 : créer et publier les modules

Un module représente une capacité IA réutilisable. Il peut contenir plusieurs use cases.

Pour chaque use case, l'administrateur définit :

- le nom et l'objectif ;
- les données d'entrée ;
- le prompt ;
- le schéma de sortie ;
- les éventuelles sources documentaires ;
- l'endpoint API ;
- les droits nécessaires.

Exemple :

```text
Module : GPR
Use case : analyse-plainte
Endpoint : POST /api/dynamic/gpr/analyse-plainte
Entrée : texte de la plainte
Sortie : résumé, niveau de risque, réponse proposée
```

**Résultat attendu :** l'API est documentée et peut être consommée par une organisation cliente.

**Si le module n'est pas publié :** aucune application externe ne peut l'utiliser.

### Étape 5 : surveiller la plateforme

L'administrateur consulte :

- les appels réussis ;
- les appels en erreur ;
- les temps de réponse ;
- les modèles utilisés ;
- les résultats en attente de validation ;
- les événements d'audit ;
- les consommations par projet.

**Résultat attendu :** les incidents d'accès, de configuration ou de modèle sont détectés rapidement.

## 5. Parcours de l'administrateur d'une organisation cliente

### Étape 1 : créer un projet externe

L'administrateur crée un projet représentant une application, une équipe ou un service de son organisation.

Exemple :

```text
Projet : Gestion des plaintes de l'Entreprise A
Application cliente : portail-support
Environnement : test
```

**Résultat attendu :** le projet possède une identité propre et peut recevoir des droits et des clés API.

### Étape 2 : choisir les modules et APIs

L'administrateur sélectionne les modules publiés dont son organisation a besoin.

Il vérifie :

- que le module répond au besoin ;
- que l'API est publiée ;
- que les données demandées sont disponibles ;
- que le résultat convient à l'application cliente.

**Résultat attendu :** les capacités IA sont associées au projet externe.

### Étape 3 : définir le contrat d'API

L'administrateur et l'équipe technique valident :

- l'URL de l'API ;
- la méthode HTTP ;
- les en-têtes requis ;
- le format du body ;
- les champs obligatoires ;
- le format de la réponse ;
- les codes d'erreur ;
- les limites d'utilisation.

**Résultat attendu :** l'équipe technique sait exactement comment intégrer l'API.

### Étape 4 : configurer les documents et le contexte

Si le use case doit utiliser des informations internes, l'administrateur configure une base de connaissances et y ajoute les documents autorisés.

Exemples :

- procédures ;
- contrats ;
- règlements ;
- textes réglementaires ;
- guides internes.

**Résultat attendu :** l'IA peut rechercher les documents pertinents lors d'un appel.

### Étape 5 : créer les accès API

L'administrateur crée une clé API associée au projet.

Il définit :

- le nom de la clé ;
- l'environnement ;
- les scopes ;
- la date d'expiration ;
- les limites par minute ou par jour.

**Règle de sécurité :** la clé est conservée uniquement côté serveur dans l'application cliente. Elle ne doit jamais être exposée dans le navigateur, le code public ou une application mobile non protégée.

**Résultat attendu :** seule l'application autorisée peut appeler les APIs du projet.

### Étape 6 : tester l'intégration

L'équipe technique appelle l'API avec des données de test.

Elle vérifie :

- l'authentification ;
- les droits ;
- la validation des données ;
- le format de la réponse ;
- les erreurs ;
- le temps de réponse ;
- l'utilisation des documents ;
- l'enregistrement de l'exécution.

**Résultat attendu :** l'application cliente reçoit une réponse exploitable.

### Étape 7 : activer le projet

Après validation :

- le projet passe en environnement actif ;
- la clé de production est créée ;
- les endpoints autorisés peuvent être appelés ;
- les appels sont tracés ;
- les résultats sont disponibles dans l'historique.

**Si le projet, le module ou l'endpoint n'est pas actif :** l'appel est refusé ou retourne une erreur de configuration.

## 6. Parcours de l'équipe technique cliente

### Étape 1 : récupérer les informations d'intégration

L'équipe reçoit :

- l'URL de l'API ;
- le chemin de l'endpoint ;
- la méthode HTTP ;
- la clé API ;
- l'identifiant du projet ;
- les scopes ;
- le schéma d'entrée ;
- le schéma de sortie ;
- les limites d'utilisation.

### Étape 2 : appeler une API ModulAI

Exemple de requête :

```http
POST /api/dynamic/gpr/analyse-plainte
Authorization: Bearer <API_KEY>
Content-Type: application/json
X-Project-Id: <PROJECT_ID>
```

```json
{
  "client": "Client Exemple",
  "date": "2026-09-15",
  "complaint": "Texte de la plainte"
}
```

### Étape 3 : traitement par ModulAI

Pour chaque appel, ModulAI :

1. identifie le projet ;
2. vérifie la clé API ;
3. vérifie les scopes et les limites ;
4. vérifie que l'endpoint est publié ;
5. vérifie les données reçues ;
6. charge le prompt et le schéma de sortie ;
7. charge les règles de sécurité ;
8. recherche les documents si le RAG est activé ;
9. sélectionne le provider et le modèle ;
10. exécute le Core AI ;
11. enregistre l'exécution et l'audit ;
12. renvoie la réponse à l'application cliente.

### Étape 4 : recevoir la réponse

Exemple de réponse réussie :

```json
{
  "status": "success",
  "module": "gpr",
  "use_case": "analyse-plainte",
  "result": {
    "summary": "Résumé de la plainte",
    "risk_level": "high",
    "proposed_response": "Réponse proposée"
  },
  "rag_context_used": true
}
```

L'application cliente décide ensuite comment afficher, stocker ou faire valider le résultat.

### Étape 5 : gérer les erreurs

L'application cliente doit distinguer :

- clé API invalide ou expirée ;
- accès interdit ;
- projet non actif ;
- endpoint inexistant ;
- module non publié ;
- données invalides ;
- limite d'utilisation dépassée ;
- fournisseur IA indisponible ;
- erreur d'exécution.

Une réponse en erreur ne doit jamais être présentée comme un résultat IA valide.

## 7. Parcours de l'utilisateur métier

L'utilisateur métier travaille principalement dans l'application de son organisation.

### Étape 1 : utiliser une fonction métier

Exemple :

```text
Ouvrir une plainte client
  → cliquer sur « Analyser la plainte »
```

### Étape 2 : fournir les informations

L'application collecte les informations nécessaires, puis appelle l'API ModulAI.

L'utilisateur n'a pas besoin de connaître :

- la clé API ;
- l'URL technique ;
- le fournisseur ;
- le modèle ;
- le prompt.

### Étape 3 : consulter le résultat

L'application affiche le résultat produit par ModulAI, par exemple :

- un résumé ;
- un niveau de risque ;
- des éléments importants ;
- une réponse proposée ;
- les sources utilisées.

### Étape 4 : vérifier et décider

L'utilisateur vérifie que le résultat correspond au dossier réel.

Il peut :

- accepter le résultat ;
- le modifier ;
- demander une nouvelle analyse ;
- le transmettre à un responsable ;
- signaler une erreur.

La décision finale appartient à l'organisation cliente et à ses utilisateurs autorisés.

## 8. Parcours direct dans l'interface ModulAI

Certains utilisateurs peuvent aussi avoir accès à l'interface ModulAI pour tester, contrôler ou valider une exécution :

```text
Se connecter
  → choisir un projet
  → choisir un module
  → choisir un use case
  → saisir les données
  → lancer l'analyse
  → consulter le résultat
  → valider ou demander une nouvelle analyse
```

Ce parcours est une interface de contrôle et de test. Le parcours principal de production reste l'appel API depuis l'application externe.

## 9. Cycle complet d'un appel API

```text
1. L'utilisateur agit dans l'application cliente
2. L'application prépare les données
3. Le serveur client ajoute la clé API et l'identifiant du projet
4. Il appelle un endpoint ModulAI publié
5. ModulAI authentifie et autorise le projet
6. ModulAI valide les données reçues
7. Le Core charge le prompt, les règles et le contexte
8. Le Core recherche les documents si nécessaire
9. Le modèle IA génère la réponse
10. ModulAI enregistre l'exécution et l'audit
11. L'API renvoie une réponse structurée
12. L'application cliente affiche ou traite le résultat
13. L'utilisateur vérifie et décide
```

## 10. Erreurs et décisions

### Le projet n'est pas accessible

Le projet n'a pas le droit d'utiliser l'API, ou sa clé est invalide.

**Action :** l'administrateur de l'organisation vérifie la clé, les scopes, l'environnement et le statut du projet.

### Le endpoint n'existe pas

Le chemin utilisé par l'application ne correspond pas à un endpoint publié.

**Action :** comparer le contrat d'API et la configuration du module.

### Le module n'est pas publié

Le module est en préparation ou désactivé.

**Action :** l'administrateur ModulAI doit le tester puis le publier.

### Les données sont invalides

Un champ obligatoire manque ou ne respecte pas le format attendu.

**Action :** l'application cliente corrige la requête avant de la renvoyer.

### Le fournisseur IA est indisponible

Le Core ne peut pas obtenir de réponse du provider ou du modèle.

**Action :** l'administrateur ModulAI vérifie le fournisseur, le modèle et les règles de fallback.

### Le résultat est incomplet ou incohérent

Les données, le prompt, le modèle ou les documents peuvent être inadaptés.

**Action :**

1. vérifier les données transmises ;
2. relancer si nécessaire ;
3. signaler le résultat ;
4. demander une vérification de la configuration ;
5. imposer une validation humaine si le domaine est sensible.

## 11. Résumé par rôle

### Administrateur ModulAI

```text
Configurer les fournisseurs
  → ajouter les modèles
  → définir les règles
  → créer et publier les modules
  → surveiller la plateforme
```

### Administrateur de l'organisation cliente

```text
Créer un projet externe
  → choisir les APIs
  → configurer les données et documents
  → créer les clés et droits
  → tester l'intégration
  → activer le projet
```

### Équipe technique cliente

```text
Recevoir le contrat d'API
  → appeler l'endpoint
  → traiter la réponse
  → gérer les erreurs
  → intégrer le résultat dans l'application
```

### Utilisateur métier

```text
Utiliser l'application de son organisation
  → fournir les informations
  → demander une analyse
  → lire le résultat
  → vérifier
  → valider ou demander une nouvelle analyse
```

## 12. Principe de responsabilité

ModulAI fournit une capacité d'intelligence artificielle via API. L'organisation cliente reste responsable des données envoyées, de l'utilisation de la réponse et de la décision finale, notamment pour les usages juridiques, financiers, médicaux, réglementaires ou à fort impact.
