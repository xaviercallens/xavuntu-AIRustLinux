# 🚀 RunuX GPU Compute Mini-OS : Feuille de Route Stratégique (Roadmap)

## 1. Vision & Objectifs

Cette feuille de route définit la trajectoire de transformation du noyau **RunuX** en un **Mini-Système d'Exploitation Bare-Metal ultra-léger et formellement vérifié**, spécialisé pour les appliances de calcul intensif, les serveurs d'inférence/entraînement Edge AI et les clusters GPU souverains.

### Objectifs Clés
1. **Empreinte Minimale (< 12 Mo)** : Temps de démarrage < 30 ms en hyperviseur ou bare-metal sans daemon superflu.
2. **Tolérance Zéro aux Pannes (`#![no_std]`, No Panics)** : Allocations faillibles, gestion stricte des erreurs et garanties formelles Lean 4.
3. **Throughput Maximal & Zéro-Copie** : Support du Resizable BAR (ReBAR), Heterogeneous Memory Management (HMM), GPUDirect Storage (GDS).
4. **Cloisonnement & Sécurité IOMMU** : Isolation cryptographique et matérielle des canaux DMA, interdisant formellement l'accès du GPU à l'espace Ring 0 du noyau hôte.
5. **Compatibilité Écosystème IA** : Compatibilité binaire ioctl avec le runtime Open Kernel Module de NVIDIA et AMD KFD pour exécuter PyTorch, vLLM, TensorRT-LLM, et llama.cpp sans modification de l'espace utilisateur.

---

## 2. Piliers d'Architecture

```
+-----------------------------------------------------------------------------------+
|               User Space : RunuX AI Engine / vLLM / PyTorch / CUDA / HIP          |
+-----------------------------------------------------------------------------------+
                                         |
                            (ioctl /dev/dri/renderD128)
                                         v
+-----------------------------------------------------------------------------------+
| RunuX GPU Subsystem (Phase 13)                                                    |
|  +---------------------+  +------------------------+  +------------------------+  |
|  | DRM Core & GEM/TTM  |  | HMM & Unified Memory   |  | Hardware Fence Sync    |  |
|  | Buffer Allocator    |  | Page Migration Engine  |  | Monotonic Progress     |  |
|  +---------------------+  +------------------------+  +------------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
| RunuX IOMMU & Hardware Isolation Layer                                            |
|  +-------------------------------------+  +------------------------------------+  |
|  | Intel VT-d / AMD-Vi Page Tables     |  | SafeDmaQueue & Ring Buffer Engine  |  |
|  | (Strict Ring 0 Containment)         |  | (Modulo-bounded, Zero Overrun)     |  |
|  +-------------------------------------+  +------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
| Hardware : PCIe Gen 4/5 | NVLink | CXL 2.0 | Resizable BAR | VRAM (HBM3 / GDDR6)  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Jalons & Calendrier de Développement

### 📍 Jalon 1 : Fondations Matérielles PCIe, ReBAR & Protection IOMMU (Phase 13.1)
* **Périmètre** : Énumération PCI Express Gen 4/5, configuration des fenêtres MMIO 64-bit et Resizable BAR (permettant au CPU de mapper l'intégralité de la VRAM GPU).
* **Isolation IOMMU** : Initialisation des tables de pages VT-d / AMD-Vi avec domaine DMA dédié au périphérique d'accélération.
* **Garantie Formelle** : Théorème d'isolation DMA interdisant tout accès DMA direct dans la mémoire noyau Ring 0 (`iommu_dma_isolation_guarantee`).

### 📍 Jalon 2 : Gestion Mémoire Hétérogène (HMM & GEM/TTM) (Phase 13.2)
* **Périmètre** : Implémentation du sous-système de mémoire unifiée (Unified Virtual Addressing - UVA) et de la migration dynamique de pages (`PageMigrationEngine`).
* **GEM / TTM Allocator** : Gestionnaire d'objets mémoires graphiques en Rust `#![no_std]` gérant VRAM locale, GTT (Graphics Translation Table) et mémoire système.
* **Garantie Formelle** : Preuve d'absence d'aliasing et de validité atomique des translations virtuelles-physiques (`hmm_address_translation_safe`).

### 📍 Jalon 3 : Moteur de Soumission & Synchronisation (DRM & DMA Fences) (Phase 13.3)
* **Périmètre** : Ring buffers matériels pour la soumission de commandes de calcul (Compute Command Queues).
* **Synchronisation Matérielle** : Primitive `DmaFence` modélisant les verrous asynchrones matériels avec progression strictement ordonnée.
* **Garantie Formelle** : Preuve de monotonie des clôtures et garantie d'absence de deadlock (`dma_fence_monotonicity`).

### 📍 Jalon 4 : Interface Système & Couche de Compatibilité Runtime (Phase 13.4)
* **Périmètre** : Exposition des périphériques `/dev/dri/card0` et `/dev/dri/renderD128`.
* **Compatibilité ioctl** : Implémentation du protocole DRM ioctl standard (`DRM_IOCTL_VERSION`, `DRM_IOCTL_GEM_CLOSE`, `DRM_IOCTL_SYNCOBJ_WAIT`, et ioctl propriétaires NVIDIA/AMDGPU).
* **Intégration** : Validation d'un micro-runtime CUDA / HIP compilé statiquement sous RunuX.

### 📍 Jalon 5 : Multi-Tenancy & Partitionnement Matériel (MIG / Slicing) (Phase 13.5)
* **Périmètre** : Support du découpage matériel de GPU (ex: Multi-Instance GPU / SR-IOV) pour isoler les charges d'inférence concurrentes.
* **Garantie Formelle** : Preuve mathématique de non-interférence et de cloisonnement total des partitions mémoire et des moteurs de calcul (`mig_tenant_isolation`).

### 📍 Jalon 6 : I/O Haute Performance & GPUDirect Storage (GDS) (Phase 13.6)
* **Périmètre** : Transfert DMA direct entre contrôleur NVMe (`SafeDmaQueue`) et VRAM sans passage par la mémoire système (Zero-Copy P2P DMA).
* **Benchmark Cible** : Débit de chargement des poids de modèles LLM saturant la bande passante PCIe Gen 5 (> 50 Go/s).
