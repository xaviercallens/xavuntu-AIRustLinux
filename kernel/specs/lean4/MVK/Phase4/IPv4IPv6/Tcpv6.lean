namespace MVK.Phase4.IPv4IPv6.Tcpv6

/-!
  # Formal Specifications for TCP IPv6 (tcp_ipv6)
  
  This module defines the properties, preconditions (requires!), and
  postconditions (ensures!) for the functions in `tcp_ipv6`.
-/

def EINVAL : Int := -22
def EAFNOSUPPORT : Int := -97

/--
  `tcp_v6_pre_connect` bounds.
-/
structure PreConnectParams where
  addr_len : Int

def pre_connect_requires (p : PreConnectParams) : Prop :=
  p.addr_len >= 0

def pre_connect_ensures (p : PreConnectParams) (result : Int) : Prop :=
  result <= 0

theorem pre_connect_valid (p : PreConnectParams) (h : pre_connect_requires p) :
  let result := if p.addr_len < 28 then EINVAL else 0;
  pre_connect_ensures p result := by
  intro result
  dsimp [result, EINVAL, pre_connect_ensures]
  split
  · -- case addr_len < 28
    decide
  · -- case addr_len >= 28
    decide

/--
  `tcp_v6_connect` bounds.
-/
structure ConnectParams where
  sk_is_null : Bool
  uaddr_is_null : Bool
  addr_len : Int
  sin6_family : Int

def connect_requires (p : ConnectParams) : Prop :=
  p.sk_is_null = false ∧
  p.uaddr_is_null = false ∧
  p.addr_len >= 0

def connect_ensures (p : ConnectParams) (result : Int) : Prop :=
  result <= 0 ∨ result = EINVAL ∨ result = EAFNOSUPPORT

theorem connect_valid (p : ConnectParams) (h : connect_requires p) :
  let result :=
    if p.addr_len < 28 then EINVAL
    else if p.sin6_family ≠ 10 then EAFNOSUPPORT
    else 0;
  connect_ensures p result := by
  intro result
  dsimp [result, EINVAL, EAFNOSUPPORT, connect_ensures]
  split
  · -- case addr_len < 28
    right; left; rfl
  · -- case addr_len >= 28
    split
    · -- case sin6_family != 10
      right; right; rfl
    · -- case sin6_family == 10
      left; decide

end MVK.Phase4.IPv4IPv6.Tcpv6
