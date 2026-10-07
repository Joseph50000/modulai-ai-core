# Phase 0 — Cadrage minimal de l’intégration GPR dans ModulAI

## Objectif

Savoir quelles capacités existent, ce que ModulAI peut réutiliser et quelles vérifications minimales éviteront de migrer à l’aveugle.

**Règle d’architecture :** ModulAI est la plateforme modulaire pour plusieurs projets. Le Core AI reste générique. Aucune logique, route, prompt, catégorie ou règle métier GPR ne doit être codée en dur dans le Core. Les capacités GPR sont intégrées comme services/modules appelés via les mécanismes génériques de ModulAI.

## État

**TERMINÉE le 5 octobre 2026 pour le cadrage nécessaire au démarrage.**

Le [compte-rendu de cadrage](./ETAT-CADRAGE-PHASE-0-MIGRATION-CORE-GPR-VERS-MODULAI.md) contient l’inventaire, les révisions examinées, les recouvrements, les frontières et la baseline des tests.

## Travail effectué

1. Repérage des routes et capacités présentes dans `gpr_ai_service`.
2. Comparaison avec le Gateway, le contrat canonique, le resolver, l’orchestration et le RAG existants dans ModulAI.
3. Confirmation de la séparation entre Core générique et logique des services/modules GPR.
4. Exécution des validations existantes disponibles : 3 tests du Core ModulAI réussis, build frontend réussi, 6 anomalies préexistantes observées dans la suite de 81 tests GPR.

## Critères de sortie

- Les capacités à intégrer et les fonctions réutilisables de ModulAI sont identifiées.
- Le Core AI est explicitement protégé contre toute spécialisation GPR.
- La baseline existante est enregistrée pour comparaison ultérieure.

Ces critères sont satisfaits. Les choix détaillés de fournisseur, de données, de compatibilité et de déploiement seront traités uniquement lorsqu’ils sont nécessaires à l’implémentation d’un service concerné ; ils ne bloquent pas la Phase 0.

## Suite immédiate

Passer à l’implémentation, en commençant par le socle générique nécessaire pour enregistrer, configurer et appeler un service/module via le contrat ModulAI. Ne pas créer un framework générique plus large que les besoins du premier service. Le choix du premier service et les critères de son contrat seront fixés avec l’utilisateur avant modification fonctionnelle.
