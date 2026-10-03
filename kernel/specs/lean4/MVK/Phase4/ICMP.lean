import MVK.Phase2.Common

namespace MVK.Phase4.ICMP

/-! # ICMP Properties -/

/-- `icmpv6_err` requires `skb` is not null -/
axiom icmpv6_err_requires_skb_not_null (skb : Option SkBuff) :
  skb.isSome

/-- `icmp6_send` requires `skb` is not null -/
axiom icmp6_send_requires_skb_not_null (skb : Option SkBuff) :
  skb.isSome

end MVK.Phase4.ICMP
