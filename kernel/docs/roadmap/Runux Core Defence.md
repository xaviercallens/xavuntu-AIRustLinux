Voici la spécification technique détaillée articulée sur l'existant (`rust-linux-mini-kernel`, `ai_bridge`, `ai_runtime`) et structurée selon la roadmap de défense active.

---

### Spécification fonctionnelle et technique : Runux Core Defenses

#### 1. Architecture du pipeline d'interception et filtrage

Le filtrage opère avant la table de dispatch standard des 297 modules. Tout appel système entrant traverse la couche de décision avant validation formelle.

```
                  ┌──────────────────────────────────────────────────────────┐
                  │                 Espace Utilisateur / VM                  │
                  └─────────────────────────────┬────────────────────────────┘
                                                │ Syscall (seccomp/eBPF hook)
                                                ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Noyau Runux (Rust bare-metal)                                                              │
│                                                                                            │
│   ┌───────────────────────┐       Verdit        ┌──────────────────────────────────────┐   │
│   │ crates/ebpf_firewall  │◀────────────────────│ crates/ai_detector                   │   │
│   │ (Contrôle d'accès LMS)│                     │ (TinyML GGUF/INT4 RVV SIMD)          │   │
│   └───────────┬───────────┘                     └──────────────────▲───────────────────┘   │
│               │ Valide                                             │ Vecteur de features   │
│               ▼                                                    │ (séquences mmap/exec) │
│   ┌───────────────────────┐                     ┌──────────────────┴───────────────────┐   │
│   │ Tables Syscall C-ABI  │                     │ crates/ai_bridge                     │   │
│   │ (crates/sys_*)        │                     │ (Ring buffer zero-copy & DMA)        │   │
│   └───────────┬───────────┘                     └──────────────────────────────────────┘   │
│               │                                                                            │
│               ▼                                                                            │
│   ┌───────────────────────┐                     ┌──────────────────────────────────────┐   │
│   │ Preuves Lean 4        │────────────────────▶│ crates/immutable_logs                │   │
│   │ (Invariants de state) │    Audit trail      │ (Merkle tree Append-Only sans heap)  │   │
│   └───────────────────────┘                     └──────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────────┘

```

---

#### 2. Spécification des modules prioritaires

##### Module `crates/ebpf_firewall`

* **Objectif** : Inspection dynamique en Ring 0 des vecteurs d'attaque polymorphiques générés par IA (injections shellcode, transitions ROP, patterns `mprotect(PROT_EXEC)` illégitimes).
* **Interface interne** :
```rust
#[repr(C)]
pub struct SyscallAuditEvent {
    pub pid: u32,
    pub syscall_nr: u32,
    pub args: [u64; 6],
    pub ip: u64,
    pub entropy_score: u16, // Détection d'entropie du payload binaire
}

pub trait SyscallFilter {
    fn evaluate(&self, ctx: &SyscallAuditEvent) -> Verdict;
}

#[repr(u8)]
pub enum Verdict {
    Pass = 0,
    InspectDeep = 1, // Redirection vers ai_detector
    BlockKill = 2,
    Rollback = 3,    // Déclenche auto_repair
}

```



##### Module `crates/ai_detector` & Liaison `ai_bridge`

* **Objectif** : Exécuter un classifieur TinyML (quantifié INT4/INT8) sous contrainte temps-réel (< 15 µs) sans bloquer les interruptions de niveau machine.
* **Mécanique** :
* Échantillonnage glissant sur les 16 derniers syscalls par PID.
* Exploitation de `matmul_rvv_f32` (vectoriel RISC-V) ou AVX-512 (x86_64) isolé du contexte CPU utilisateur.
* Zéro allocation dynamique via un pool pré-alloué `StaticTensorPool` validé par la Phase 2 (Slab/Memory safety).



##### Module `crates/immutable_logs`

* **Objectif** : Journalisation d'audit inviolable même sous compromission root.
* **Mécanique** :
* Structure en arbre de Merkle append-only in-memory.
* Ancrage cryptographique périodique par signature Ed25519 (via instructions scalaires RISC-V Zk).
* Synchronisation en direct vers une enclave matérielle ou un nœud de consensus externe via les abstractions `crates/net`.



---

#### 3. Formalisation Lean 4 : Définition de l'invariant de confinement

Ce contrat formel étend la Phase 8 (Scheduling) et la Phase 9 (Memory) pour garantir qu'aucun processus classé hostile ne peut muter une page noyau.

```lean
-- Formalisation de l'état de sécurité du noyau Runux
structure KernelMemoryRegion where
  base_addr : Nat
  length    : Nat
  is_kernel : Bool
  writable  : Bool

structure ProcessSecurityContext where
  pid        : Nat
  is_jailed  : Bool
  trust_rank : Nat -- 0 (malveillant/suspect), 1 (sandbox), 2 (root/certifié)

def IsValidAccess (ctx : ProcessSecurityContext) (region : KernelMemoryRegion) (write_req : Bool) : Prop :=
  if region.is_kernel then
    -- Une région noyau ne peut jamais être écrite par un processus bridé ou suspect
    write_req = false ∧ (ctx.trust_rank ≥ 2 ∨ ¬ctx.is_jailed)
  else
    True

-- Théorème de non-contamination des structures du noyau
theorem kernel_isolation_guarantee
  (ctx : ProcessSecurityContext)
  (region : KernelMemoryRegion)
  (h_kernel : region.is_kernel = true)
  (h_suspect : ctx.trust_rank = 0) :
  IsValidAccess ctx region true ↔ False := by
  dsimp [IsValidAccess]
  rw [h_kernel]
  simp [h_suspect]

```

---

#### 4. Plan de travail pour l'étape 1 (`ebpf_firewall` + `ai_detector`)

* **Sprint 1 : Interface Hook & Ring Buffer**
* Implémenter l'interception non-bloquante au niveau de `crates/sys_call/src/dispatch.rs`.
* Mapper la sortie de l'intercepteur vers un buffer circulaire sans verrou (*lock-free SP/SC ring buffer*).


* **Sprint 2 : Moteur d'inférence TinyML bare-metal**
* Adapter `crates/ai_runtime` pour charger des poids de modèle gelés statiquement compilés (`rodata`).
* Valider les contraintes de latence d'inférence (< 20 µs) sur SpacemiT K1 et x86_64.


* **Sprint 3 : Validation de robustesse**
* Écrire la suite de tests unitaires injectant des traces d'attaques polymorphes générées par LLM.
* Vérifier l'absence de régression de débit réseau (`crates/net`) avec le filtre activé.



Souhaites-tu démarrer par le câblage direct du hook d'interception dans `crates/sys_*`, ou par la structure interne du ring buffer lock-free pour `ai_bridge` ?