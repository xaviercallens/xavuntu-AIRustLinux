#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]
use kernel_types::*;

// SyncWrapper for safe global mutability
#[repr(transparent)]
pub struct SyncWrapper<T>(pub core::cell::UnsafeCell<T>);
unsafe impl<T> Sync for SyncWrapper<T> {}
impl<T> SyncWrapper<T> {
    pub const fn new(value: T) -> Self {
        Self(core::cell::UnsafeCell::new(value))
    }
    #[inline(always)]
    pub unsafe fn get_mut(&self) -> &mut T {
        // SAFETY: The caller must guarantee exclusive access or single-threaded context.
        unsafe { &mut *self.0.get() }
    }
}

use core::ffi::c_void;

#[repr(C)]
pub struct sk_buff_compat {
    pub data: *mut u8,
    pub len: u32,
    pub cb: [u8; 48],
}

/// Calculate UDP checksum for IPv6 packets
///
/// # Safety
/// - `skb` must be a valid sk_buff pointer
/// - `proto` must be a valid protocol number
/// - `len` must be the correct length of the data
/// - `saddr` and `daddr` must be valid IPv6 addresses
/// - `sk` must be a valid inet_sock pointer
#[no_mangle]
pub unsafe extern "C" fn ip6_udp_checksum(
    skb: *mut sk_buff,
    proto: c_int,
    len: c_int,
    saddr: *const in6_addr,
    daddr: *const in6_addr,
    sk: *mut inet_sock,
) -> c_int {
    if skb.is_null() || saddr.is_null() || daddr.is_null() || sk.is_null() {
        return -EINVAL;
    }

    if proto < 0 || proto > u8::MAX as c_int || len < 0 {
        return -EINVAL;
    }

    let _sk = &mut *sk;
    let skb_compat = &mut *(skb as *mut sk_buff_compat);

    let udp_len: usize = len as usize;
    if udp_len > skb_compat.len as usize {
        return -EINVAL;
    }

    let udp_offset = UDP_SKB_CB(skb);
    if udp_offset < 0 {
        return udp_offset;
    }
    let udp_offset = udp_offset as usize;

    let saddr = &*saddr;
    let daddr = &*daddr;

    let mut csum: u32 = 0;

    for i in 0..4 {
        csum = csum.wrapping_add(u32::from_be(saddr.in6_u.u6_addr32[i]));
        csum = csum.wrapping_add(u32::from_be(daddr.in6_u.u6_addr32[i]));
    }

    csum = csum.wrapping_add((proto as u8) as u32);
    csum = csum.wrapping_add((udp_len as socklen_t) as u32);

    // Add UDP header and data
    let data_ptr = (*skb).data as *const u8;
    let udp_data = core::slice::from_raw_parts(data_ptr, udp_len);

    let mut i = 0usize;
    while i < udp_len {
        let word = if i + 1 < udp_len {
            u16::from_be_bytes([udp_data[i], udp_data[i + 1]])
        } else {
            u16::from_be_bytes([udp_data[i], 0])
        };
        csum = csum.wrapping_add(word as u32);
        i += 2;
    }

    while (csum >> 16) != 0 {
        csum = (csum & 0xFFFF) + (csum >> 16);
    }

    let check = !(csum as u16);

    // Store checksum in UDP header
    let udp_header = ((*skb).data as *mut udphdr).add(udp_offset);
    (*udp_header).check = check;

    0
}

/// Calculate offset for UDP control block in sk_buff
///
/// # Safety
/// - `skb` must be a valid sk_buff pointer
#[no_mangle]
pub unsafe extern "C" fn UDP_SKB_CB(skb: *mut sk_buff) -> c_int {
    if skb.is_null() {
        return -EINVAL;
    }

    let skb = &*skb;
    let cb = skb.cb.as_ptr() as *const c_void;
    let udp_cb = cb.add(4) as *const c_int;
    unsafe { *udp_cb }
}

// Rename static variables to follow Rust's naming conventions
pub static __UDP_DISCONNECT: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());
pub static ICMPV6_ERR_CONVERT: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());
pub static INET6_SOCKRAW_OPS: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());
pub static IP6_DATAGRAM_CONNECT_V6_ONLY: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());
pub static IP6_DATAGRAM_RECV_COMMON_CTL: SyncWrapper<*mut core::ffi::c_void> = SyncWrapper::new(core::ptr::null_mut());

// Ensure FFI compatibility
extern "C" {
    // Import necessary functions and types from the kernel_types crate
    pub fn ip6_datagram_connect_v6_only(sk: *mut sock, uaddr: *mut sockaddr, addr_len: socklen_t) -> c_int;
    pub fn ip6_datagram_recv_common_ctl(sk: *mut sock, msg: *mut msghdr, len: c_int, off: c_int) -> c_int;
    // ... other necessary functions and types
}


#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
