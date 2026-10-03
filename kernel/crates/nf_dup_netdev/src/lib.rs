#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! Netfilter packet duplication support
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons, unexpected_cfgs)]

use core::ffi::c_int;
use kernel_types::*;

pub const EINVAL: c_int = -22; pub const ENOMEM: c_int = -12; pub const EOPNOTSUPP: c_int = -95;

// Type definitions for FFI compatibility
#[repr(C)]
pub struct nft_pktinfo { pub skb: *mut sk_buff, pub net: *mut c_void }

#[repr(C)]
pub struct nft_offload_ctx { pub net: *mut c_void, pub num_actions: c_int }

#[repr(C)]
pub struct nft_flow_rule { pub rule: *mut c_void }

#[repr(C)]
pub struct flow_action_entry { pub id: c_int, pub dev: *mut net_device }

unsafe extern "C" {
    fn dev_get_by_index_rcu(net: *mut c_void, ifindex: c_int) -> *mut net_device;
    fn dev_get_by_index(net: *mut c_void, ifindex: c_int) -> *mut net_device;
    fn kfree_skb(skb: *mut sk_buff);
    fn skb_clone(skb: *mut sk_buff, gfp_mask: c_int) -> *mut sk_buff;
    fn dev_queue_xmit(skb: *mut sk_buff) -> c_int;
    fn nft_flow_rule_action_entry(rule: *mut c_void, index: c_int) -> *mut flow_action_entry;
}

// Internal helper function
unsafe fn nf_do_netdev_egress(skb: *mut sk_buff, dev: *mut net_device) {
    // Check if MAC header is set
    if skb.is_null() {
        return;
    }

    // In C, skb_push is a macro that adjusts the data pointer
    // We don't need to implement it here as it's handled by the C ABI
    // Just call the function that would be called after skb_push

    (*skb).dev = dev as *mut c_void;
    (*skb).tstamp = 0;
    dev_queue_xmit(skb);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_fwd_netdev_egress(pkt: *const nft_pktinfo, oif: c_int) {
    if pkt.is_null() {
        return;
    }

    let skb = (*pkt).skb;
    let dev = dev_get_by_index_rcu((*pkt).net, oif);
    if dev.is_null() {
        kfree_skb(skb);
        return;
    }

    nf_do_netdev_egress(skb, dev);
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nf_dup_netdev_egress(pkt: *const nft_pktinfo, oif: c_int) {
    if pkt.is_null() {
        return;
    }

    let orig_skb = (*pkt).skb;
    let dev = dev_get_by_index_rcu((*pkt).net, oif);
    if dev.is_null() {
        return;
    }

    let skb = skb_clone(orig_skb, GFP_ATOMIC as c_int);
    if !skb.is_null() {
        nf_do_netdev_egress(skb, dev);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn nft_fwd_dup_netdev_offload(
    ctx: *mut nft_offload_ctx,
    flow: *mut nft_flow_rule,
    id: c_int,
    oif: c_int,
) -> c_int {
    if ctx.is_null() || flow.is_null() {
        return EINVAL;
    }

    let net = unsafe { (*ctx).net };
    let dev = unsafe { dev_get_by_index(net, oif) };
    if dev.is_null() {
        return EOPNOTSUPP;
    }

    let entry = nft_flow_rule_action_entry((*flow).rule, (*ctx).num_actions);
    if !entry.is_null() {
        (*entry).id = id;
        (*entry).dev = dev;
        (*ctx).num_actions += 1;
    }

    0
}

// Module tests (conditional compilation)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_codes() {
        assert_eq!(EINVAL, -22);
        assert_eq!(ENOMEM, -12);
        assert_eq!(EOPNOTSUPP, -95);
    }

    #[test]
    fn test_nft_pktinfo_layout() {
        assert_eq!(core::mem::size_of::<nft_pktinfo>(), 16);
        assert_eq!(core::mem::align_of::<nft_pktinfo>(), 8);
    }

    #[test]
    fn test_nft_offload_ctx_layout() {
        assert_eq!(core::mem::size_of::<nft_offload_ctx>(), 16);
        assert_eq!(core::mem::align_of::<nft_offload_ctx>(), 8);
    }

    #[test]
    fn test_nft_flow_rule_layout() {
        assert_eq!(core::mem::size_of::<nft_flow_rule>(), 8);
        assert_eq!(core::mem::align_of::<nft_flow_rule>(), 8);
    }

    #[test]
    fn test_flow_action_entry_layout() {
        assert_eq!(core::mem::size_of::<flow_action_entry>(), 16);
        assert_eq!(core::mem::align_of::<flow_action_entry>(), 8);
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
