import MVK.Phase2.Common

namespace MVK.Phase4.UDP

/-! # UDP Properties -/

/-- `udp_v6_get_port` requires `sk` is not null -/
axiom udp_v6_get_port_requires_sk_not_null (sk : Option Socket) (snum : UInt16) :
  sk.isSome

/-- `udp_v6_rehash` requires `sk` is not null -/
axiom udp_v6_rehash_requires_sk_not_null (sk : Option Socket) :
  sk.isSome

/-- `udp6_skb_len` requires `skb` is not null -/
axiom udp6_skb_len_requires_skb_not_null (skb : Option SkBuff) :
  skb.isSome

/-- `udpv6_recvmsg` requires `sk` and `msg` are not null -/
axiom udpv6_recvmsg_requires_not_null (sk : Option Socket) (msg : Option MsgHdr) :
  sk.isSome ∧ msg.isSome

end MVK.Phase4.UDP
