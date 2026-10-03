# 🛠️ Plan d'Implémentation Détaillé : RunuX GPU Compute Engine

Ce document détaille l'ensemble des tâches d'ingénierie, les structures C ABI, les crates Rust `#![no_std]` et les critères d'acceptation technique pour doter RunuX du sous-système de calcul GPU bare-metal.

---

## 1. Vue d'Ensemble des Crates

| Crate | Responsabilité | Dépendances | Target Invariant |
| :--- | :--- | :--- | :--- |
| `crates/gpu_types` | Types fondamentaux, structures C ABI, flags ReBAR, descripteurs de paquets | `core` | Bit-exact C ABI (`#[repr(C)]`) |
| `crates/pci_express` | Énumération PCIe Gen 4/5, configuration ReBAR, allocation des fenêtres MMIO | `gpu_types`, `kernel_types` | Zero-warning `#![no_std]` |
| `crates/iommu_vtd` | Tables de pages IOMMU VT-d / AMD-Vi, domaines d'isolation DMA, barrières de protection Ring 0 | `gpu_types`, `memory_alloc` | Fallible alloc, strict isolation |
| `crates/gpu_memory` | Heterogeneous Memory Management (HMM), Unified Virtual Addressing (UVA), GEM/TTM allocator | `gpu_types`, `iommu_vtd` | No-aliasing, safe page migration |
| `crates/drm_core` | Gestionnaire DRM bare-metal, ring buffers de commandes, clôtures matérielles (`SafeDmaFence`) | `gpu_types`, `gpu_memory` | Monotonic fence progression |
| `crates/gpu_ioctl` | Table de dispatch ioctl pour `/dev/dri/renderD128` et `/dev/dri/card0` | `drm_core`, `syscall_table` | Pre-dispatch filtered, zero panic |

---

## 2. Découpage Précis des Tâches (Tasks)

### Tâche 1 : Spécifications Formelles Mathématiques en Lean 4 (Phase 13)
* **Objectif** : Modéliser et prouver formellement sans omission (zéro `sorry`) la sécurité mémoire et l'isolation matérielle du sous-système GPU.
* **Fichiers** :
  * [`specs/lean4/MVK/Phase13/GpuCompute.lean`](file:///home/xavkal/xdev/rust-linux-mini-kernel/specs/lean4/MVK/Phase13/GpuCompute.lean)
  * Intégration dans [`specs/lean4/MVK.lean`](file:///home/xavkal/xdev/rust-linux-mini-kernel/specs/lean4/MVK.lean)
* **Théorèmes requis** :
  1. `iommu_dma_isolation_guarantee` : Aucun descripteur DMA GPU ne peut cibler une adresse de la région noyau Ring 0.
  2. `hmm_address_translation_safe` : L'adresse virtuelle résolue par le moteur de translation d'adresse (ATS) pointe soit vers la RAM hôte soit vers la VRAM, sans collision ni double allocation.
  3. `dma_fence_monotonicity` : La séquence des fences matérielles est strictement croissante, éliminant les interblocages (deadlocks).
  4. `mig_tenant_isolation` : Les partitions matérielles multi-locataires sont mutuellement exclusives ($P_1 \cap P_2 = \emptyset$).
* **Critère d'acceptation** : `lake build` compile avec 0 erreur et 0 warning dans le nouveau module.

---

### Tâche 2 : Définition des Types C ABI & Structures Matérielles (`crates/gpu_types`)
* **Objectif** : Établir la couche FFI bit-exact pour les descripteurs PCIe, IOMMU et paquets GPU.
* **Structures à implémenter** :
  ```rust
  #[repr(C)]
  #[derive(Debug, Clone, Copy, PartialEq, Eq)]
  pub struct PciBarConfig {
      pub bar_index: u8,
      pub is_64bit: bool,
      pub is_prefetchable: bool,
      pub base_address: u64,
      pub size_bytes: u64,
  }

  #[repr(C)]
  #[derive(Debug, Clone, Copy)]
  pub struct GpuDmaDescriptor {
      pub host_physical_addr: u64,
      pub device_vram_addr: u64,
      pub byte_count: u32,
      pub flags: u32,
      pub fence_seq: u64,
  }

  #[repr(C)]
  #[derive(Debug, Clone, Copy, PartialEq, Eq)]
  pub struct DmaFenceHandle {
      pub context_id: u32,
      pub seqno: u64,
      pub is_signaled: bool,
  }
  ```
* **Critère d'acceptation** : `cargo test` validant les tailles (`core::mem::size_of`) et alignements stricts.

---

### Tâche 3 : Moteur IOMMU & Isolation DMA (`crates/iommu_vtd`)
* **Objectif** : Implémenter le contrôleur de translation d'adresse I/O (Intel VT-d / AMD-Vi).
* **Sous-tâches** :
  1. Allocation de la table de contexte racine IOMMU (Root Table & Context Table).
  2. Configuration du domaine DMA restreint pour le GPU (interdisant la plage `0xFFFF800000000000..=0xFFFFFFFFFFFFFFFF`).
  3. Barrière matérielle invalidant le cache IOTLB lors des changements de mapping.
* **Garantie** : En cas de tentative d'écriture DMA hors domaine, le contrôleur déclenche une interruption d'erreur IOMMU interceptée par le noyau sans panique.

---

### Tâche 4 : Moteur de Mémoire Hétérogène (HMM & GEM/TTM) (`crates/gpu_memory`)
* **Objectif** : Coordonner le partage d'adresses virtuelles et la migration de pages entre CPU et GPU.
* **Sous-tâches** :
  1. `UnifiedMemorySpace` : Mapping unifié permettant à un pointeur dans l'espace utilisateur d'être accédé indistinctement par les cœurs CPU et les Tensor Cores du GPU.
  2. `PageMigrationEngine` : Mécanisme de migration automatique déclenché par un page fault matériel GPU (ATS / Page Migration via PCIe ATS/PRI).
  3. Gestionnaire TTM : Arbitrage automatique entre la VRAM rapide et la mémoire hôte (eviction/swap vers Host RAM en cas de saturation de la VRAM).
* **Gestion des erreurs** : Retourne systématiquement `Result<(), AllocError>` ou `-ENOMEM`.

---

### Tâche 5 : Ring Buffers de Commandes & Synchronisation (`crates/drm_core`)
* **Objectif** : Permettre l'envoi asynchrone de batchs d'instructions de calcul et la synchronisation via fences.
* **Sous-tâches** :
  1. `ComputeRingBuffer` : File circulaire protégée contre les dépassements mémoire (`SafeDmaQueue` conforme au théorème Lean 4).
  2. `DmaFenceManager` : Gestionnaire de synchronisation gérant les dépendances d'exécution inter-streams.
  3. Gestion du timeout matériel : En cas de GPU Hang (kernel shader infini), mécanisme de réinitialisation logicielle de l'anneau de soumission (GPU Soft Reset).

---

### Tâche 6 : Couche ioctl & Exposition Périphérique (`crates/gpu_ioctl`)
* **Objectif** : Offrir l'interface standard Linux `/dev/dri/renderD128` pour les runtimes d'inférence.
* **Commandes ioctl supportées** :
  * `DRM_IOCTL_VERSION` (0xC0406400)
  * `DRM_IOCTL_GEM_CREATE` (0xC010640B)
  * `DRM_IOCTL_GEM_MMAP` (0xC020640E)
  * `DRM_IOCTL_SYNCOBJ_WAIT` (0xC02064BF)
  * Extension propriétaire RunuX : `RUNUX_GPU_IOCTL_SUBMIT_TENSOR`
* **Sécurité** : Chaque appel ioctl est audité par le filtre eBPF / LMS avant dispatch dans le pilote.

---

## 3. Matrice de Traçabilité des Exigences

| Exigence | Description | Implémentation Rust | Preuve Lean 4 |
| :--- | :--- | :--- | :--- |
| **REQ-GPU-001** | Isolation Ring 0 contre les DMA GPU | `crates/iommu_vtd` | `iommu_dma_isolation_guarantee` |
| **REQ-GPU-002** | Mémoire Unifiée sans Aliasing | `crates/gpu_memory` | `hmm_address_translation_safe` |
| **REQ-GPU-003** | Progression ordonnée des Fences | `crates/drm_core` | `dma_fence_monotonicity` |
| **REQ-GPU-004** | Cloisonnement Multi-Tenant (MIG) | `crates/gpu_scheduler` | `mig_tenant_isolation` |
| **REQ-GPU-005** | Zéro-Panic & Allocations Faillibles | Partout (`Result<T, E>`) | Vérifié par audit Clippy & Miri |
