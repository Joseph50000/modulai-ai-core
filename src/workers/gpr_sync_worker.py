import sys
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler

# Ajouter la racine du projet ai-core-fastapi au sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from src.rag.vector_store import GenericVectorStore

logger = logging.getLogger(__name__)

def fetch_gpr_data():
    """
    Simule la récupération des données métier GPR depuis la base MySQL.
    (Remplacement de l'ancien appel de sync_service.py)
    """
    return [
        {
            "id": 1,
            "objet_categorie": "Facturation",
            "motif_reclamation": "Double débit",
            "texte_plainte": "J'ai été débité deux fois de la même facture.",
            "statut_final": "Résolu",
            "texte_solution": "Remboursement du trop perçu effectué."
        },
        {
            "id": 2,
            "objet_categorie": "Technique",
            "motif_reclamation": "Panne",
            "texte_plainte": "Ma box internet redémarre en boucle depuis hier soir.",
            "statut_final": "Résolu",
            "texte_solution": "Remplacement du matériel planifié."
        }
    ]

def perform_gpr_sync():
    """
    Tâche asynchrone pour indexer la base métier GPR dans le Vector Store générique.
    C'est ici que s'opère le formatage spécifique métier vers le format texte brut RAG.
    """
    logger.info("Début de la synchronisation GPR vers RAG...")
    data = fetch_gpr_data()
    
    if not data:
        logger.info("Aucune donnée GPR à synchroniser.")
        return

    documents = []
    metadatas = []
    ids = []
    
    for row in data:
        doc_id = f"gpr_claim_{row.get('id')}"
        cat = row.get("objet_categorie", "")
        mot = row.get("motif_reclamation", "")
        txt = row.get("texte_plainte", "")
        sol = row.get("texte_solution", "")
        
        # Formatage métier spécifique pour que l'IA comprenne le contexte
        combined_text = f"Plainte ({cat} - {mot}): {txt} \nSolution apportée: {sol}"
        
        meta = {
            "source_id": row.get("id"),
            "categorie": str(cat).lower(),
            "motif": str(mot).lower(),
            "statut": str(row.get("statut_final", ""))
        }
        
        ids.append(doc_id)
        documents.append(combined_text)
        metadatas.append(meta)
        
    store = GenericVectorStore(collection_name="gpr_claims")
    store.upsert_documents(documents=documents, metadatas=metadatas, ids=ids)
    
    logger.info(f"Synchronisation GPR terminée. Total indexé: {len(documents)}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    # Synchronisation prévue tous les jours à 02:00
    scheduler.add_job(perform_gpr_sync, 'cron', hour=2, minute=0)
    scheduler.start()
    logger.info("Worker GPR: Planificateur Cron démarré (02:00 AM).")
    return scheduler

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    perform_gpr_sync()
