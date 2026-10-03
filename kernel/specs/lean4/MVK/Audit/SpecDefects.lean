import MVK.Phase1.ArchSetup
import MVK.Phase4.ARP

/-!
Machine-checked evidence for specification defects found by the v12
oracle-gated proof-completion pilot (docs/roadmap/units_status.csv).
Each theorem below proves the *universal closure* of a still-`sorry`
statement is false, so no proof of the original can exist as written.
-/

namespace MVK.Audit.SpecDefects

open ARP in
theorem arp_send_safety_statement_is_false :
    Not (forall (skb : Option sk_buff) (ip : Option Nat) (result : Int),
        arp_send_safety_preconditions skb ip = true ->
        arp_send_safety_postconditions result) := by
  intro h
  have h1 := h (some (sk_buff.mk (some (net_device.mk 1)) none none)) (some 0) 1 rfl
  simp [arp_send_safety_postconditions] at h1

open MVK.Phase1.ArchSetup in
theorem interrupts_disabled_after_init_statement_is_false :
    Not (forall state : ArchState,
        state.success = true -> state.interrupts_disabled = true) := by
  intro h
  have h1 := h (ArchState.mk false false false false true) rfl
  simp at h1

end MVK.Audit.SpecDefects
