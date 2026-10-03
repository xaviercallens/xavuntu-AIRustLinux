#!/usr/bin/env python3
"""
KAL Redis Long-Term Memory (LTM) Manager & Context CLI for Xavuntu.

Provides commands to:
- stats: View Redis connectivity, memory footprint, and LTM fact counts.
- add-fact: Insert a durable fact with semantic embedding into Redis LTM.
- search: Perform semantic similarity search across stored facts.
- prune-context: Simulate AttentionMatter adaptive context pruning on a multi-turn conversation.
- sync-seed: Seed default Sovereign Xavuntu system memories into Redis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from anse.memory.redis_ltm import RedisLongTermMemoryManager


def get_manager() -> RedisLongTermMemoryManager:
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    return RedisLongTermMemoryManager(redis_host=host, redis_port=port)


def cmd_stats(args: argparse.Namespace) -> None:
    mgr = get_manager()
    stats = mgr.stats()
    print("=== KAL REDIS LONG-TERM MEMORY (LTM) STATUT ===")
    print(f"Connexion Redis : {'🟢 CONNECTÉ' if stats['redis_connected'] else '🔴 DÉCONNECTÉ'}")
    print(f"Hôte / Port     : {stats['redis_host']}:{stats['redis_port']}")
    print(f"Faits Durables  : {stats['total_durable_facts']} enregistrés")
    print(f"Facteur Décroissance : {stats['decay_factor']} (0.95^âge)")
    print(f"Budget Ratio    : {stats['token_budget_ratio'] * 100:.0f}%")
    if stats.get("redis_memory"):
        print(f"RAM Redis       : {stats['redis_memory'].get('used_memory_human', 'N/A')}")
    print("Moteur Contextuel : AttentionMatter + Redis Persistent Hash/Set")


def cmd_add_fact(args: argparse.Namespace) -> None:
    mgr = get_manager()
    fact = mgr.insert_fact(
        text=args.text,
        source_session=args.session,
        importance=args.importance,
    )
    print(f"✅ Fait mémorisé avec succès dans Redis LTM [ID: {fact.fact_id}] :")
    print(f"   '{fact.text}'")


def cmd_search(args: argparse.Namespace) -> None:
    mgr = get_manager()
    q_vec = mgr.embedding_service.embed(args.query)
    results = mgr.search_ltm(q_vec, top_k=args.top_k)
    print(f"=== RÉSULTATS RECHERCHE SÉMANTIQUE LTM ({len(results)} trouvés) ===")
    for rank, (score, fact) in enumerate(results, 1):
        print(f"[{rank}] Score: {score:.4f} | ID: {fact.fact_id} | Session: {fact.source_session}")
        print(f"    Texte: {fact.text}")


def cmd_prune(args: argparse.Namespace) -> None:
    mgr = get_manager()
    res = mgr.build_pruned_context(session_id=args.session, query=args.query, token_budget=args.budget)
    print("=== ÉLAGAGE CONTEXTUEL ATTENTIONMATTER ===")
    print(f"Requête       : {res.query}")
    print(f"Tokens Totaux : {res.total_tokens} / Budget: {res.budget_limit}")
    print(f"Économie      : {res.tokens_saved} tokens ({res.reduction_ratio}% réduction)")
    print(f"Faits Inclus  : {len(res.selected_memories)}")
    print(f"Tours Inclus  : {len(res.selected_history)}")
    print("\n--- PROMPT ASSEMBLÉ ---\n")
    print(res.assembled_prompt)


def cmd_seed(args: argparse.Namespace) -> None:
    mgr = get_manager()
    seed_facts = [
        "L'utilisateur principal et architecte souverain du système Xavuntu est Xavier Callens.",
        "Le noyau de calcul est RunuX v13.0 écrit en Rust, doté d'une arène TPU ReBAR de 16 Go.",
        "L'intelligence Système 2 souveraine est GWAYA-Qwen 14B T4 avec accélération TPU.",
        "Le moteur réflexe Système 1 est GWAYA-Qwen 3.8-Quant opérant les commandes vocales KAL 9000.",
        "Le bouclier cybernétique sovereign enforce un durcissement noyau strict et zéro-trust.",
        "L'algorithme AttentionMatter préserve les faits critiques avec décroissance temporelle de 0.95.",
    ]
    added = 0
    for fact_text in seed_facts:
        mgr.insert_fact(fact_text, source_session="bootstrap_seed", importance=1.2)
        added += 1
    print(f"✅ {added} faits fondamentaux injectés dans Redis Long-Term Memory.")


def main() -> None:
    parser = argparse.ArgumentParser(description="KAL Redis LTM Context Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="Statistiques de la mémoire Redis LTM")
    p_stats.set_defaults(func=cmd_stats)

    p_add = sub.add_parser("add-fact", help="Ajouter un fait durable à la mémoire LTM")
    p_add.add_argument("text", help="Contenu textuel du fait")
    p_add.add_argument("--session", default="default", help="Identifiant de session source")
    p_add.add_argument("--importance", type=float, default=1.0, help="Coefficient d'importance (default 1.0)")
    p_add.set_defaults(func=cmd_add_fact)

    p_search = sub.add_parser("search", help="Recherche sémantique vectorielle dans LTM")
    p_search.add_argument("query", help="Requête textuelle de recherche")
    p_search.add_argument("--top-k", type=int, default=5, help="Nombre max de résultats")
    p_search.set_defaults(func=cmd_search)

    p_prune = sub.add_parser("prune-context", help="Élaguer et assembler le contexte prompt")
    p_prune.add_argument("query", help="Requête utilisateur actuelle")
    p_prune.add_argument("--session", default="default", help="Session ID")
    p_prune.add_argument("--budget", type=int, default=2048, help="Budget de tokens max")
    p_prune.set_defaults(func=cmd_prune)

    p_seed = sub.add_parser("seed", help="Injecter les mémoires fondamentales souveraines")
    p_seed.set_defaults(func=cmd_seed)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
