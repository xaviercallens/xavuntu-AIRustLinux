# Parallel Code Improvement - Final Report

**Generated:** 2026-05-17 12:14:38
**Total Duration:** 4.1 minutes
**Model:** Azure OpenAI GPT-5.3-codex

---

## Executive Summary

### Overall Results

| Metric | Value |
|--------|-------|
| **Total Modules** | 122 |
| **Successful** | 1 (0.8%) |
| **Failed** | 121 (99.2%) |
| **Total Errors Fixed** | 0 |
| **Avg Improvement** | 0.0% if successful else 0.0% |
| **Total Commits** | 0 |

### Performance

| Metric | Value |
|--------|-------|
| **Total Duration** | 4.1 minutes |
| **Avg per Module** | 2.0 seconds |
| **Throughput** | 1764.8 modules/hour |
| **Retry Rate** | 1.98 retries/module |

---

## Detailed Results

### Top 20 Improvements

| Rank | Module | Errors Fixed | Improvement % | Duration | Attempts | Commit |
|------|--------|--------------|---------------|----------|----------|--------|
| 1 | kernel_types | 0 | 0.0% | 0.5s | 1 | N/A |

### Failed Modules

| Module | Initial Errors | Attempts | Duration |
|--------|----------------|----------|----------|
| ping | 146 | 3 | 0.9s |
| esp4_offload | 145 | 3 | 0.7s |
| nf_nat_helper | 76 | 3 | 0.6s |
| xfrm6_input | 67 | 3 | 0.5s |
| nf_conntrack_amanda | 60 | 3 | 0.6s |
| reassembly | 58 | 3 | 0.5s |
| fib_rules | 55 | 3 | 0.6s |
| nf_conntrack_proto | 53 | 3 | 0.5s |
| xfrm6_tunnel | 50 | 3 | 0.6s |
| bpf_tcp_ca | 45 | 3 | 0.6s |
| seg6_local | 42 | 3 | 0.5s |
| nf_conntrack_seqadj | 37 | 3 | 0.6s |
| netfilter | 35 | 3 | 0.7s |
| seg6_hmac | 35 | 3 | 0.6s |
| nf_conntrack_standalone | 34 | 3 | 0.5s |
| mip6 | 31 | 3 | 0.5s |
| nf_conntrack_ecache | 31 | 3 | 0.4s |
| ndisc | 30 | 3 | 0.7s |
| exthdrs | 30 | 3 | 0.6s |
| gre_offload | 28 | 3 | 0.6s |
| nf_conntrack_h323_asn1 | 28 | 3 | 0.6s |
| nf_conntrack_proto_icmp | 27 | 3 | 0.5s |
| nf_conntrack_pptp | 26 | 3 | 0.6s |
| nf_conntrack_proto_gre | 25 | 3 | 0.8s |
| calipso | 25 | 3 | 0.5s |
| xfrm6_policy | 25 | 3 | 0.7s |
| udp_offload | 25 | 3 | 0.4s |
| ipcomp6 | 24 | 3 | 0.7s |
| xfrm6_protocol | 23 | 3 | 0.5s |
| gre_demux | 21 | 3 | 0.5s |
| core | 21 | 3 | 0.5s |
| nf_conntrack_irc | 21 | 3 | 0.5s |
| ip6_flowlabel | 21 | 3 | 0.6s |
| nf_nat_irc | 20 | 3 | 0.5s |
| nf_conntrack_expect | 20 | 3 | 0.5s |
| af_inet6 | 20 | 3 | 0.6s |
| fou6 | 20 | 3 | 0.6s |
| nf_conntrack_proto_sctp | 19 | 3 | 0.5s |
| fou | 19 | 3 | 0.7s |
| nf_log | 19 | 3 | 0.4s |
| inet_connection_sock | 18 | 3 | 0.7s |
| nf_nat_proto | 18 | 3 | 0.5s |
| ip6_vti | 17 | 3 | 0.6s |
| datagram | 17 | 3 | 0.7s |
| tunnel6 | 16 | 3 | 0.5s |
| tcp_ipv6 | 15 | 3 | 0.5s |
| fib6_notifier | 15 | 3 | 0.6s |
| xfrm6_output | 14 | 3 | 0.5s |
| nf_conncount | 13 | 3 | 0.7s |
| icmp | 13 | 3 | 0.5s |
| nf_conntrack_proto_tcp | 13 | 3 | 0.5s |
| fib_trie | 13 | 3 | 0.6s |
| seg6_iptunnel | 12 | 3 | 0.6s |
| tcpv6_offload | 11 | 3 | 0.6s |
| exthdrs_core | 11 | 3 | 0.6s |
| route | 10 | 3 | 2.2s |
| ip6_input | 9 | 3 | 0.5s |
| nf_dup_netdev | 9 | 3 | 0.5s |
| ip6_fib | 9 | 3 | 0.5s |
| ipv6_sockglue | 8 | 3 | 0.7s |
| ip6_tunnel | 8 | 3 | 0.5s |
| seg6 | 8 | 3 | 0.6s |
| mcast | 7 | 3 | 0.5s |
| fib_frontend | 7 | 3 | 0.7s |
| fib_notifier | 7 | 3 | 0.7s |
| nf_conntrack_ftp | 7 | 3 | 0.6s |
| ip6mr | 7 | 3 | 0.5s |
| nf_conntrack_proto_icmpv6 | 6 | 3 | 0.7s |
| igmp | 6 | 3 | 0.4s |
| nf_conntrack_proto_dccp | 4 | 3 | 0.4s |
| inet6_hashtables | 3 | 3 | 0.7s |
| mcast_snoop | 3 | 3 | 0.6s |
| nf_conntrack_netlink | 3 | 3 | 0.7s |
| xfrm6_state | 3 | 3 | 0.6s |
| cipso_ipv4 | 3 | 3 | 0.6s |
| nf_conntrack_helper | 2 | 3 | 0.6s |
| nf_conntrack_snmp | 2 | 3 | 0.5s |
| nf_conntrack_proto_generic | 2 | 3 | 0.6s |
| sit | 1 | 3 | 0.7s |
| ip6_offload | 0 | 3 | 0.6s |
| ip6_gre | 0 | 3 | 0.7s |
| esp4 | 0 | 3 | 0.6s |
| nf_conntrack_tftp | 0 | 3 | 0.6s |
| udp | 0 | 3 | 0.5s |
| fib_semantics | 0 | 3 | 0.5s |
| nf_conntrack_sip | 0 | 3 | 0.6s |
| nf_conntrack_sane | 0 | 3 | 0.4s |
| inet6_connection_sock | 0 | 3 | 0.5s |
| nf_nat_amanda | 0 | 3 | 0.8s |
| nf_nat_ftp | 0 | 3 | 0.5s |
| syncookies | 0 | 3 | 0.7s |
| nf_conntrack_proto_udp | 0 | 3 | 0.6s |
| esp6_offload | 0 | 3 | 0.7s |
| nf_conntrack_acct | 0 | 3 | 0.7s |
| ip6_output | 0 | 3 | 0.6s |
| anycast | 0 | 3 | 0.4s |
| nf_conntrack_h323_main | 0 | 3 | 0.4s |
| output_core | 0 | 3 | 0.5s |
| nf_conntrack_core | 0 | 3 | 0.4s |
| nf_conntrack_broadcast | 0 | 3 | 0.4s |
| ip6_icmp | 0 | 3 | 0.5s |
| ip6_checksum | 0 | 3 | 0.5s |
| nf_conntrack_timeout | 0 | 3 | 0.5s |
| devinet | 0 | 3 | 0.5s |
| nf_conntrack_extend | 0 | 3 | 0.5s |
| af_inet | 0 | 3 | 0.6s |
| nf_conntrack_timestamp | 0 | 3 | 0.6s |
| udplite | 0 | 3 | 0.7s |
| esp6 | 0 | 3 | 0.7s |
| nf_conntrack_netbios_ns | 0 | 3 | 0.7s |
| rpl | 0 | 3 | 0.5s |
| arp | 0 | 3 | 0.6s |
| exthdrs_offload | 0 | 3 | 0.4s |
| sysctl_net_ipv6 | 0 | 3 | 0.4s |
| fib6_rules | 0 | 3 | 0.4s |
| raw | 0 | 3 | 0.5s |
| nf_log_syslog | 0 | 3 | 0.5s |
| nf_nat_core | 0 | 3 | 0.4s |
| nf_flow_table_inet | 0 | 3 | 0.3s |
| ip6_udp_tunnel | 0 | 3 | 0.6s |
| nf_nat_masquerade | 0 | 3 | 0.5s |

---

## Git Integration

**Total Commits:** 0

```bash
# Push all changes
git push origin master

# View commit history
git log --oneline -n 0
```

---

## Recommendations

1. ⚠️  **121 modules failed** - Review and retry with different approach
2. ⚠️  **High retry rate** - Consider improving error detection or model prompts

---

**Report Generated:** 2026-05-17T12:14:38.810736
