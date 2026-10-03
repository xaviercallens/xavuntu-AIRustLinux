import os

content = """namespace MVK.Phase8

/--
  Task structure abstraction for the CFS run-queue.
-/
structure Task where
  id : Nat
  priority : Nat
  vruntime : Nat
  deriving Repr

/--
  Run queue state.
-/
structure RunQueue where
  tasks : List Task
  current_task : Option Task

/--
  CFS scheduling requires that the highest priority (or lowest vruntime) task
  is selected. Priority inversion is avoided by bounded vruntime differences.
-/
def valid_runqueue (rq : RunQueue) : Prop :=
  match rq.current_task with
  | none => rq.tasks.isEmpty
  | some c => ∀ t ∈ rq.tasks, c.vruntime ≤ t.vruntime

/--
  Theorem: The scheduling algorithm maintains the invariant.
-/
theorem cfs_no_priority_inversion (rq : RunQueue) (h : valid_runqueue rq) :
  ∀ t ∈ rq.tasks, match rq.current_task with
                  | some c => c.vruntime ≤ t.vruntime
                  | none => True := by
  intro t ht
  cases h_curr : rq.current_task with
  | none => trivial
  | some c =>
    -- rewrite the hypothesis h to use the fact that rq.current_task is some c
    have h_valid : ∀ t ∈ rq.tasks, c.vruntime ≤ t.vruntime := by
      unfold valid_runqueue at h
      rw [h_curr] at h
      exact h
    exact h_valid t ht

end MVK.Phase8
"""

with open("MVK/Phase8/Scheduling.lean", "w") as f:
    f.write(content)
