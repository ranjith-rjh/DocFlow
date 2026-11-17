#!/usr/bin/env bash
# Vérifie la connectivité du réseau privé DocFlow entre le Mac et la VM Fedora.
#
# À lancer depuis le Mac, VM démarrée :
#     ./scripts/verifier_reseau.sh            # réseau seul (phase P1)
#     ./scripts/verifier_reseau.sh --services # + RabbitMQ et PostgreSQL (application lancée)
#
# Les adresses peuvent être surchargées par variables d'environnement :
#     FEDORA_IP=192.168.56.10 MAC_IP=192.168.56.1 ./scripts/verifier_reseau.sh
#
# Code de sortie : 0 si tous les tests passent, 1 sinon.

set -u

FEDORA_IP="${FEDORA_IP:-192.168.56.10}"
MAC_IP="${MAC_IP:-192.168.56.1}"
SERVICES="${1:-}"
echecs=0

# Affiche OK/ECHEC pour une commande donnée, sans interrompre le script.
verifier() {
    local libelle="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf '  [OK]    %s\n' "$libelle"
    else
        printf '  [ECHEC] %s\n' "$libelle"
        echecs=$((echecs + 1))
    fi
}

echo "== Réseau privé DocFlow (Fedora attendue en ${FEDORA_IP}) =="

echo "1. Côté Mac"
verifier "le Mac possède l'adresse ${MAC_IP}" sh -c "ifconfig | grep -q 'inet ${MAC_IP} '"
verifier "ping Mac -> Fedora"                 ping -c 2 -t 3 "${FEDORA_IP}"
verifier "port SSH 22 ouvert sur Fedora"      nc -z -G 3 "${FEDORA_IP}" 22

echo "2. Depuis un conteneur Docker (comme le feront MS1/MS2)"
if docker info >/dev/null 2>&1; then
    verifier "ping conteneur -> Fedora" docker run --rm alpine:3.20 ping -c 2 -W 3 "${FEDORA_IP}"
else
    printf '  [ECHEC] Docker Desktop ne répond pas (est-il lancé ?)\n'
    echecs=$((echecs + 1))
fi

if [ "${SERVICES}" = "--services" ]; then
    echo "3. Services applicatifs"
    verifier "RabbitMQ écoute sur ${MAC_IP}:5672 (pour MS3)"   nc -z -G 3 "${MAC_IP}" 5672
    verifier "PostgreSQL ouvert sur ${FEDORA_IP}:5432"         nc -z -G 3 "${FEDORA_IP}" 5432
    verifier "PostgreSQL joignable depuis un conteneur"        \
        docker run --rm alpine:3.20 nc -z -w 3 "${FEDORA_IP}" 5432
    verifier "API DocFlow en bonne santé (base + messagerie)"  curl -sf http://localhost:8000/health
fi

echo
if [ "${echecs}" -eq 0 ]; then
    echo "Tous les tests sont passés."
    exit 0
fi
echo "${echecs} test(s) en échec."
exit 1
