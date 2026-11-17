# Installation de la VM Fedora (nœud B)

> Objectif : une VM Fedora ARM64 joignable **en permanence** à l'adresse
> `192.168.56.10`, depuis le Mac **et depuis les conteneurs Docker**, avec ou
> sans Wi-Fi (cahier des charges §5.3, NF-03, T-10).
>
> Ce guide couvre la VM, le réseau, SSH et le pare-feu. PostgreSQL et MS3
> seront installés dans une étape ultérieure.
>
> VirtualBox se configure dans l'**interface graphique**. Les libellés peuvent
> varier légèrement selon la langue de VirtualBox (7.2.22 sur ce Mac).

## 0. Fiche d'identité

| Élément | Valeur |
|---|---|
| Nom de la VM | **`docflow-vm`** |
| ISO | **Fedora Workstation, aarch64**, dernière version stable (« Live ISO ») — <https://fedoraproject.org/workstation/download> |
| Version installée | **Fedora release 45 (Forty Five)** — vérifiée le 2026-11-16 |
| Type / Version | `Linux` / `Fedora (ARM 64-bit)` |
| Processeurs | **4** vCPU (le Mac en a 12) |
| Mémoire vive | **8192 Mo** (le Mac a 24 Go ; il en faut pour macOS et Docker) |
| Disque | **40 Go**, VDI, dynamique (le Mac a 87 Go libres) |
| Mémoire vidéo | **Maximum proposé** (bureau GNOME) |
| Nom d'hôte | **`docflow-vm`** |
| Utilisateur | **`dfadmin`** (administrateur) |
| Carte réseau 1 | **NAT** — Internet pour les mises à jour |
| Carte réseau 2 | **Réseau hôte uniquement `HostNetwork`** (existant) |
| Adresse MAC carte 2 | **`080027DF0010`** |
| IP du Mac | **`192.168.56.1`** |
| IP de la VM | **`192.168.56.10/24`**, statique |
| Connexion NetworkManager | **`docflow-net`** |
| Zone pare-feu | **`docflow`** : SSH (22) + PostgreSQL (5432) uniquement |

---

## 1. Réseau hôte uniquement (VirtualBox, côté Mac)

On garde le réseau existant **`HostNetwork`**, déjà validé lors de tes tests :
masque `255.255.255.0`, plage `192.168.56.1` – `192.168.56.199`. Rien à créer.

> **Point d'attention :** l'adresse fixe `.10` de la VM est dans la plage DHCP
> de `HostNetwork`. Sans risque tant que `docflow-vm` est la seule VM sur ce
> réseau. Si un jour une autre VM s'y branche en DHCP, abaisser la limite
> supérieure à `192.168.56.9` (Fichier → Outils → Gestionnaire de réseau →
> Réseaux hôte uniquement → `HostNetwork`).

---

## 2. Créer la VM

**Nouvelle** :

| Section | Réglage |
|---|---|
| Nom et système | Nom **`docflow-vm`**, Image ISO = l'ISO Workstation aarch64, Type `Linux`, Version `Fedora (ARM 64-bit)` |
| Installation sans surveillance | **Cocher « Ignorer l'installation sans surveillance »** |
| Matériel | **8192 Mo**, **4** processeurs (EFI reste activé) |
| Disque dur | **Créer un disque virtuel**, **40 Go**, VDI, ne pas pré-allouer |

**Terminer sans démarrer.**

## 3. Configurer la VM (VM éteinte → Configuration)

**Affichage → Écran** : mémoire vidéo au **maximum**.

**Réseau → Carte 1** :
- Activer la carte : ✅
- Mode d'accès : **NAT**

**Réseau → Carte 2** :
- Activer la carte : ✅
- Mode d'accès : **Réseau hôte uniquement** (*Host-only Network*)
- Nom : **`HostNetwork`**
- **Avancé** → Adresse MAC : **`080027DF0010`**, câble branché ✅

**OK**.

---

## 4. Installer Fedora Workstation

1. Démarrer la VM → *Start Fedora Workstation Live*.
2. Choisir **Install Fedora** (*Installer sur le disque dur*).
3. Langue et clavier : **Français**. Destination : le disque de 40 Go, **effacer / utiliser tout le disque**.
4. Installer, puis **redémarrer**. Si la VM redémarre sur le Live, éteindre et
   retirer l'ISO : Configuration → Stockage → lecteur optique → *Retirer le disque*.
5. Assistant de premier démarrage de GNOME :
   - Nom complet : **`dfadmin`**, nom d'utilisateur : **`dfadmin`** (le premier compte est administrateur)
   - Mot de passe de ton choix
6. **Paramètres → Énergie** : désactiver la **mise en veille automatique**.
   Une VM en veille rendrait MS3 et PostgreSQL injoignables pendant la démo.

---

## 5. Commandes Linux (dans un Terminal de la VM)

Le strict nécessaire, dans l'ordre. Copier une ligne à la fois.

Nom d'hôte et mises à jour :

```bash
sudo hostnamectl set-hostname docflow-vm
```

```bash
sudo dnf upgrade -y
```

Pare-feu : créer la zone `docflow` avec SSH et PostgreSQL uniquement :

```bash
sudo firewall-cmd --permanent --new-zone=docflow
```

```bash
sudo firewall-cmd --permanent --zone=docflow --add-service=ssh --add-service=postgresql
```

```bash
sudo firewall-cmd --reload
```

Réseau : la connexion `docflow-net` est liée à la **MAC** de la carte 2 (pas
besoin de connaître le nom de l'interface). `never-default` laisse la route
Internet à la carte NAT.

```bash
sudo nmcli connection add type ethernet con-name docflow-net ethernet.mac-address 08:00:27:DF:00:10 ipv4.method manual ipv4.addresses 192.168.56.10/24 ipv4.never-default yes ipv6.method disabled connection.zone docflow
```

```bash
sudo nmcli connection up docflow-net
```

SSH (installé mais désactivé par défaut sur Workstation) :

```bash
sudo systemctl enable --now sshd
```

> Si `sshd` est introuvable : `sudo dnf install -y openssh-server`, puis relancer la commande.

Contrôle :

```bash
ip -br addr
```

Attendu : une interface avec **`192.168.56.10/24`**, une autre avec une adresse
NAT **`10.0.2.x`**. Puis :

```bash
ping -c 3 192.168.56.1
```

Redémarrer la VM une fois et relancer `ip -br addr` : l'adresse `.10` doit
revenir toute seule.

---

## 6. Vérifications depuis le Mac

Docker Desktop lancé, VM démarrée, dans le Terminal du Mac à la racine du projet :

```bash
./scripts/verifier_reseau.sh
```

Il vérifie : l'adresse `192.168.56.1` du Mac, le ping Mac → VM, le port SSH,
et le **ping depuis un conteneur Docker** vers la VM.

Ensuite, **couper le Wi-Fi** et relancer le script (test T-10).

Connexion SSH depuis le Mac, plus pratique ensuite :

```bash
ssh dfadmin@192.168.56.10
```

Une fois tout validé : VirtualBox → `docflow-vm` → **Instantanés → Prendre**,
nom **`base-reseau-ok`**.

---

## Dépannage

**`WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` au premier `ssh`**
Normal après une réinstallation : le Mac a gardé la clé d'une ancienne VM à
la même adresse. Vérifier d'abord que c'est bien la nouvelle VM en comparant
les empreintes :

- dans la VM : `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
- sur le Mac : `ssh-keyscan -t ed25519 192.168.56.10 | ssh-keygen -lf -`

Si elles sont identiques, oublier l'ancienne clé sur le Mac puis se reconnecter
(accepter la nouvelle empreinte avec `yes`) :

```bash
ssh-keygen -R 192.168.56.10
```

---

## Ce qu'il faut me renvoyer

1. La sortie de `ip -br addr` dans la VM.
2. La sortie de `./scripts/verifier_reseau.sh`, avec et sans Wi-Fi.
3. La version installée : `cat /etc/fedora-release`.
