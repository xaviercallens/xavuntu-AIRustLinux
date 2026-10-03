#!/bin/bash
set -e

REPO="xaviercallens/AutoevolveAI"

# 1. Vérification de la connexion Jules
echo "🔍 Vérification du client Google Jules..."
AUTH_CHECK=$(npx -y @google/jules remote list --repo 2>&1 || true)

if echo "$AUTH_CHECK" | grep -q "did you forget to login"; then
    echo "⚠️ Vous n'êtes pas encore authentifié sur Google Jules."
    echo "Pour connecter votre compte Google Ultra, exécutez dans votre terminal :"
    echo ""
    echo "   npx -y @google/jules login"
    echo ""
    echo "Ou en mode code manuel si vous êtes sur une machine distante / SSH :"
    echo "   npx -y @google/jules login --no-launch-browser"
    echo ""
    exit 1
fi

echo "✅ Authentification Google Jules active."

# 2. Définition de la Mission Complexe & God Prompt
TASK_TITLE="Mission Complexe: Implémentation du RateLimiter Distribué & Spécification Lean 4"

PROMPT="MISSION COMPLEXE D'INGÉNIERIE:
Implémente le composant de limitation de débit distribué haute performance 'anse/core/rate_limiter.py'.

EXIGENCES ARCHITECTURALES:
1. Double palier: Token Bucket mémoire local O(1) pour absorption des bursts + Sliding Window Counter asynchrone Redis (via script Lua atomique).
2. Interface asynchrone (asyncio) avec gestion transparente des déconnexions Redis (fallback local dégradé).
3. Suite de tests complète dans 'tests/test_rate_limiter.py': tests unitaires, tests de concurrence (asyncio.gather), et tests de propriétés Hypothesis (@hypothesis.given) vérifiant l'idempotence et la non-violation du plafond.
4. Spécification formelle Lean 4 dans 'formal/ANSE/RateLimiter.lean' prouvant l'invariant de non-dépassement de capacité (tokens <= capacity).
5. Validation obligatoire: exécute 'make verify-all' dans ton terminal. N'ouvre la Pull Request que si tous les tests et la compilation Lean 4 sont strictement verts sans aucun 'sorry' ni stub ('pass', 'TODO')."

echo "🚀 Envoi de la mission à Google Jules (Cloud Gemini Ultra)..."
npx -y @google/jules new --repo "$REPO" "$TASK_TITLE

$PROMPT"

echo "🎉 Mission soumise avec succès à Jules !"
echo "Pour suivre l'avancement de la session en direct :"
echo "   npx -y @google/jules remote list --session"
