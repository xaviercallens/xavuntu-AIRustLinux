#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(target_arch = "x86_64"), no_std)]

//! FTP NAT helper for Linux kernel
//!
//! This is an FFI-compatible Rust translation of the Linux kernel C implementation.
//! ABI compatibility is maintained for all exported symbols.

#![cfg_attr(not(test), no_std)]
#![cfg_attr(not(test), no_main)]
#![allow(non_camel_case_types)]
#![allow(dead_code)]
#![allow(clippy::all)]
#![allow(non_snake_case)]
#![allow(dead_code, unused_imports, non_camel_case_types, non_snake_case, unused_mut, unused_variables, unused_assignments, unused_attributes, private_interfaces, unused_comparisons)]

use core::{ffi::c_void, ptr};

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

use kernel_types::*;

pub const NF_DROP: c_int = 0x01;
pub const NF_ACCEPT: c_int = 0x02;
pub const NFPROTO_IPV4: c_int = 2;
pub const NF_CT_FTP_PORT: c_int = 0;
pub const NF_CT_FTP_PASV: c_int = 1;
pub const NF_CT_FTP_EPRT: c_int = 2;
pub const NF_CT_FTP_EPSV: c_int = 3;
pub const EBUSY: c_int = 16;

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_ct_port { pub port: u16 }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_l4proto { pub tcp: nf_ct_port }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_man_proto {
    pub tcp: nf_ct_port,
    pub u: nf_conntrack_l4proto
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_tuple { pub dst: nf_conntrack_man_proto }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conn_tuplehash {
    pub tuple: nf_conntrack_tuple,
    pub dir: c_int,
    pub expectfn: Option<unsafe extern "C" fn(*mut nf_conntrack_expect)>,
}

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_nat_helper { pub name: *const c_char }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_inet_addr { pub ip: u32, pub ip6: [u32; 4] }

#[repr(C)]
#[derive(Copy, Clone)]
pub struct nf_conntrack_expect {
    pub master: *mut nf_conn,
    pub tuple: nf_conntrack_tuple,
    pub saved_proto: nf_conntrack_man_proto,
    pub dir: c_int,
    pub expectfn: Option<unsafe extern "C" fn(*mut nf_conntrack_expect)>,
    _private: [u8; 0],
}

unsafe extern "C" {
    fn nf_ct_expect_related(exp: *mut nf_conntrack_expect, flags: c_uint) -> c_int;
    fn nf_ct_unexpect_related(exp: *mut nf_conntrack_expect);
    fn nf_ct_helper_log(skb: *mut c_void, ct: *mut nf_conn, msg: *const c_char);
    fn nf_nat_mangle_tcp_packet(
        skb: *mut c_void,
        ct: *mut nf_conn,
        ctinfo: c_int,
        protoff: c_int,
        matchoff: c_int,
        matchlen: c_int,
        buffer: *const u8,
        buflen: c_int,
    ) -> bool;
    fn nf_nat_helper_unregister(helper: *const nf_nat_helper);
    fn synchronize_rcu();
    fn RCU_INIT_POINTER(p: *mut *mut c_void, v: *mut c_void);
    static nat_helper_ftp: nf_nat_helper;
}

#[inline]
fn htons(v: u16) -> u16 { v.to_be() }

#[inline]
fn ntohs(v: u16) -> u16 { u16::from_be(v) }

#[inline]
fn CTINFO2DIR(ctinfo: c_int) -> c_int { ctinfo & 1 }

unsafe extern "C" fn nf_nat_follow_master(_exp: *mut nf_conntrack_expect) {}

fn push_byte(buf: &mut [u8], pos: &mut usize, b: u8) -> bool {
    if *pos >= buf.len() {
        return false;
    }
    buf[*pos] = b;
    *pos += 1;
    true
}

fn push_u8_dec(buf: &mut [u8], pos: &mut usize, v: u8) -> bool {
    if v >= 100 {
        let h = v / 100;
        let t = (v / 10) % 10;
        let o = v % 10;
        push_byte(buf, pos, b'0' + h) && push_byte(buf, pos, b'0' + t) && push_byte(buf, pos, b'0' + o)
    } else if v >= 10 {
        let t = v / 10;
        let o = v % 10;
        push_byte(buf, pos, b'0' + t) && push_byte(buf, pos, b'0' + o)
    } else {
        push_byte(buf, pos, b'0' + v)
    }
}

fn push_u16_dec(buf: &mut [u8], pos: &mut usize, mut v: u16) -> bool {
    let mut tmp = [0u8; 5];
    let mut n = 0usize;
    if v == 0 {
        return push_byte(buf, pos, b'0');
    }
    while v > 0 {
        tmp[n] = (v % 10) as u8;
        v /= 10;
        n += 1;
    }
    while n > 0 {
        n -= 1;
        if !push_byte(buf, pos, b'0' + tmp[n]) {
            return false;
        }
    }
    true
}

#[no_mangle]
pub unsafe extern "C" fn nf_nat_ftp_fmt_cmd(
    ct: *mut nf_conn,
    type_: c_int,
    buffer: *mut u8,
    buflen: size_t,
    addr: *mut nf_inet_addr,
    port: u16,
) -> c_int {
    if ct.is_null() || buffer.is_null() || addr.is_null() || buflen == 0 {
        return 0;
    }

    let _ct = &*ct;
    let a = &*addr;
    let out = core::slice::from_raw_parts_mut(buffer, buflen as usize);
    let mut p = 0usize;

    match type_ {
        NF_CT_FTP_PORT | NF_CT_FTP_PASV => {
            let bytes = a.ip.to_be_bytes();
            let p_high = (port >> 8) as u8;
            let p_low = (port & 0xFF) as u8;

            let _ok = push_u8_dec(out, &mut p, bytes[0])
                && push_byte(out, &mut p, b',')
                && push_u8_dec(out, &mut p, bytes[1])
                && push_byte(out, &mut p, b',')
                && push_u8_dec(out, &mut p, bytes[2])
                && push_byte(out, &mut p, b',')
                && push_u8_dec(out, &mut p, bytes[3])
                && push_byte(out, &mut p, b',')
                && push_u8_dec(out, &mut p, p_high)
                && push_byte(out, &mut p, b',')
                && push_u8_dec(out, &mut p, p_low);

            p as c_int
        },
        NF_CT_FTP_EPRT | NF_CT_FTP_EPSV => {
            // Extended EPRT/EPSV not fully implemented
            0
        }
        _ => 0,
    }
}

#[no_mangle]
pub unsafe extern "C" fn nf_nat_ftp(
    skb: *mut c_void,
    ctinfo: c_int,
    type_: c_int,
    protoff: c_int,
    matchoff: c_int,
    matchlen: c_int,
    exp: *mut nf_conntrack_expect,
) -> c_int {
    let exp = exp.as_mut().unwrap();
    let ct = (*exp).master.as_mut().unwrap();

    let dir = !CTINFO2DIR(ctinfo);
    let mut newaddr = nf_inet_addr {
        ip: 0,
        ip6: [0; 4],
    };

    (*exp).saved_proto.tcp = (*exp).tuple.dst.u.tcp;
    (*exp).dir = dir;
    (*exp).expectfn = Some(nf_nat_follow_master);

    let mut port = ntohs((*exp).saved_proto.tcp.port);
    let mut found = false;

    while port != 0 {
        (*exp).tuple.dst.u.tcp.port = htons(port);

        // Simulate nf_ct_expect_related
        if nf_ct_expect_related(exp, 0) == 0 {
            found = true;
            break;
        } else if nf_ct_expect_related(exp, 0) != -EBUSY {
            port = 0;
            break;
        }
        port += 1;
    }

    if !found {
        nf_ct_helper_log(skb, ct, b"all ports in use\0".as_ptr() as *const c_char);
        return NF_DROP;
    }

    let mut buffer = [0u8; 128];
    let buflen = nf_nat_ftp_fmt_cmd(ct, type_, buffer.as_mut_ptr(), buffer.len() as size_t, &mut newaddr as *mut nf_inet_addr, port);

    if buflen <= 0 {
        nf_ct_helper_log(skb, ct, b"cannot format command\0".as_ptr() as *const c_char);
        nf_ct_unexpect_related(exp);
        return NF_DROP;
    }

    if !nf_nat_mangle_tcp_packet(skb, ct, ctinfo, protoff, matchoff, matchlen, buffer.as_ptr(), buflen as c_int) {
        nf_ct_helper_log(skb, ct, b"cannot mangle packet\0".as_ptr() as *const c_char);
        nf_ct_unexpect_related(exp);
        return NF_DROP;
    }

    NF_ACCEPT
}

#[no_mangle]
pub unsafe extern "C" fn nf_nat_ftp_fini() {
    nf_nat_helper_unregister(NAT_HELPER_FTP.get_mut());
    RCU_INIT_POINTER(NF_NAT_FTP_HOOK.get_mut(), ptr::null_mut());
    synchronize_rcu();
}

#[no_mangle]
pub unsafe extern "C" fn nf_nat_ftp_init() -> c_int {
    if !(*NF_NAT_FTP_HOOK.get_mut()).is_null() {
        return -1; // BUG_ON
    }
    nf_nat_helper_register(NAT_HELPER_FTP.get_mut());
    RCU_INIT_POINTER(NF_NAT_FTP_HOOK.get_mut(), nf_nat_ftp as *mut c_void);
    0
}

// Helper functions
#[no_mangle]
pub unsafe extern "C" fn warn_set(_val: *const u8, _kp: *const c_void) -> c_int {
    pr_info(b"kernel >= 2.6.10 only uses 'ports' for conntrack modules\0".as_ptr() as *const u8);
    0
}

// Constants
static NAT_HELPER_NAME: &[u8] = b"ftp\0";

static NAT_HELPER_FTP: SyncWrapper<nf_nat_helper> = SyncWrapper::new(nf_nat_helper {
    name: NAT_HELPER_NAME.as_ptr() as *const c_char,
});

// Module macros
#[no_mangle]
pub static NF_NAT_FTP_HOOK: SyncWrapper<*mut c_void> = SyncWrapper::new(ptr::null_mut());

// FFI compatibility functions (only unique ones, rest from kernel_types)
#[no_mangle]
pub unsafe extern "C" fn nf_ct_l3num(_ct: *mut nf_conn) -> c_int {
    NFPROTO_IPV4
}

#[no_mangle]
pub unsafe extern "C" fn nf_nat_helper_register(_helper: *mut nf_nat_helper) {
    // Simulated implementation
}

#[no_mangle]
pub unsafe extern "C" fn pr_info(_msg: *const u8) {
    // Simulated implementation
}

// Module exports
#[no_mangle]
pub static NF_NAT_FTP_MODULE: SyncWrapper<Module> = SyncWrapper::new(Module {
    license: b"GPL\0".as_ptr() as *const u8,
    author: b"Rusty Russell <rusty@rustcorp.com.au>\0".as_ptr() as *const u8,
    description: b"ftp NAT helper\0".as_ptr() as *const u8,
});

#[repr(C)]
struct Module {
    license: *const u8,
    author: *const u8,
    description: *const u8,
}

// Helper function for formatting
unsafe fn write(buffer: *mut u8, _buflen: size_t, args: &core::fmt::Arguments) -> size_t {
    let mut writer = BufferWriter { buffer, pos: 0 };
    core::fmt::Write::write_fmt(&mut writer, *args).unwrap();
    writer.pos
}

#[repr(C)]
struct BufferWriter { buffer: *mut u8, pos: usize }

impl core::fmt::Write for BufferWriter {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        let len = s.len();
        if self.pos + len > self.buffer as usize {
            return Err(core::fmt::Error);
        }

        // SAFETY: We've checked the bounds
        unsafe {
            ptr::copy_nonoverlapping(s.as_ptr(), self.buffer.add(self.pos), len);
            self.pos += len;
        }
        Ok(())
    }
}
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // Test 1: Verify FTP NAT command-type constants have the expected values.
    // The kernel ABI depends on these being exactly 0–3 in order.
    // -----------------------------------------------------------------------
    #[test]
    fn test_ftp_command_type_constants() {
        assert_eq!(NF_CT_FTP_PORT, 0, "PORT command code must be 0");
        assert_eq!(NF_CT_FTP_PASV, 1, "PASV command code must be 1");
        assert_eq!(NF_CT_FTP_EPRT, 2, "EPRT command code must be 2");
        assert_eq!(NF_CT_FTP_EPSV, 3, "EPSV command code must be 3");
    }

    // -----------------------------------------------------------------------
    // Test 2: Verify NF_DROP / NF_ACCEPT / NFPROTO_IPV4 / EBUSY constants.
    // These are used in hook return values and error paths.
    // -----------------------------------------------------------------------
    #[test]
    fn test_nf_verdict_and_proto_constants() {
        assert_eq!(NF_DROP,       0x01, "NF_DROP must equal 1");
        assert_eq!(NF_ACCEPT,     0x02, "NF_ACCEPT must equal 2");
        assert_eq!(NFPROTO_IPV4,  2,    "NFPROTO_IPV4 must equal 2");
        assert_eq!(EBUSY,         16,   "EBUSY must equal 16");
    }

    // -----------------------------------------------------------------------
    // Test 3: nf_nat_ftp_fmt_cmd must return 0 when any pointer argument
    // is null (null-pointer rejection / EINVAL-equivalent guard).
    // -----------------------------------------------------------------------
    #[test]
    fn test_fmt_cmd_null_ct_returns_zero() {
        let mut addr = nf_inet_addr { ip: 0x0101_0101_u32.to_be(), ip6: [0; 4] };
        let mut buf = [0u8; 64];

        // SAFETY: We are deliberately passing a null `ct` pointer to exercise
        // the null-pointer guard at the top of nf_nat_ftp_fmt_cmd.  The function
        // checks `ct.is_null()` before dereferencing, so no UB occurs.
        let ret = unsafe {
            nf_nat_ftp_fmt_cmd(
                core::ptr::null_mut(),          // ct  – intentionally null
                NF_CT_FTP_PORT,
                buf.as_mut_ptr(),
                buf.len() as size_t,
                &mut addr as *mut nf_inet_addr,
                21,
            )
        };
        assert_eq!(ret, 0, "null ct must cause fmt_cmd to return 0");
    }

    // -----------------------------------------------------------------------
    // Test 4: nf_nat_ftp_fmt_cmd must return 0 when buflen == 0, preventing
    // a zero-length slice from being created inside the function.
    // -----------------------------------------------------------------------
    #[test]
    fn test_fmt_cmd_zero_buflen_returns_zero() {
        // A non-null but arbitrary ct/addr pointer is enough; the guard fires
        // before any dereference when buflen == 0.
        let mut fake_ct = core::mem::MaybeUninit::<kernel_types::nf_conn>::zeroed();
        let mut addr = nf_inet_addr { ip: 0x7f00_0001_u32.to_be(), ip6: [0; 4] };
        let mut buf = [0u8; 64];

        // SAFETY: `fake_ct` is zero-initialised; the function checks
        // `buflen == 0` before it dereferences `ct`, so no UB occurs.
        let ret = unsafe {
            nf_nat_ftp_fmt_cmd(
                fake_ct.as_mut_ptr() as *mut nf_conn,
                NF_CT_FTP_PORT,
                buf.as_mut_ptr(),
                0,                              // buflen == 0 – guard must trigger
                &mut addr as *mut nf_inet_addr,
                21,
            )
        };
        assert_eq!(ret, 0, "zero buflen must cause fmt_cmd to return 0");
    }

    // -----------------------------------------------------------------------
    // Test 5: nf_nat_ftp_fmt_cmd with NF_CT_FTP_PORT and a known IP / port
    // must produce the correct comma-separated "a,b,c,d,ph,pl" string.
    //
    // IP  = 192.168.1.10  →  bytes [192, 168, 1, 10]
    // port = 0x1000 (4096) →  ph = 16, pl = 0
    // Expected payload: "192,168,1,10,16,0"  (17 chars)
    // -----------------------------------------------------------------------
    #[test]
    fn test_fmt_cmd_port_formats_correctly() {
        let mut fake_ct = core::mem::MaybeUninit::<kernel_types::nf_conn>::zeroed();
        // 192.168.1.10 in network byte order
        let ip_host: u32 = (192 << 24) | (168 << 16) | (1 << 8) | 10;
        let mut addr = nf_inet_addr { ip: ip_host.to_be(), ip6: [0; 4] };
        let mut buf = [0u8; 64];

        // SAFETY: `fake_ct` is zero-initialised. `nf_nat_ftp_fmt_cmd` only
        // reads `*ct` after validating the pointer is non-null; zeroed memory
        // is valid for a read of the struct layout used here.
        let ret = unsafe {
            nf_nat_ftp_fmt_cmd(
                fake_ct.as_mut_ptr() as *mut nf_conn,
                NF_CT_FTP_PORT,
                buf.as_mut_ptr(),
                buf.len() as size_t,
                &mut addr as *mut nf_inet_addr,
                0x1000u16,   // port = 4096 → ph=16, pl=0
            )
        };

        let written = &buf[..ret as usize];
        let s = core::str::from_utf8(written).expect("output must be valid UTF-8");
        assert_eq!(s, "192,168,1,10,16,0",
            "PORT format for 192.168.1.10:0x1000 must be '192,168,1,10,16,0'");
    }

    // -----------------------------------------------------------------------
    // Test 6: push_u8_dec writes the correct decimal ASCII bytes for values
    // spanning all three branches (< 10, 10–99, ≥ 100).
    // -----------------------------------------------------------------------
    #[test]
    fn test_push_u8_dec_all_branches() {
        // Single digit
        let mut buf = [0u8; 8];
        let mut pos = 0usize;
        assert!(push_u8_dec(&mut buf, &mut pos, 7));
        assert_eq!(&buf[..pos], b"7");

        // Two digits
        pos = 0;
        assert!(push_u8_dec(&mut buf, &mut pos, 42));
        assert_eq!(&buf[..pos], b"42");

        // Three digits
        pos = 0;
        assert!(push_u8_dec(&mut buf, &mut pos, 255));
        assert_eq!(&buf[..pos], b"255");
    }

    // -----------------------------------------------------------------------
    // Test 7: htons / ntohs round-trip and CTINFO2DIR direction extraction.
    // -----------------------------------------------------------------------
    #[test]
    fn test_byte_order_and_ctinfo2dir() {
        // htons / ntohs must be inverses on any u16.
        let val: u16 = 0x1234;
        assert_eq!(ntohs(htons(val)), val, "ntohs(htons(x)) must equal x");

        // CTINFO2DIR extracts the LSB of ctinfo to derive the direction.
        assert_eq!(CTINFO2DIR(0), 0, "even ctinfo → direction 0 (original)");
        assert_eq!(CTINFO2DIR(1), 1, "odd ctinfo  → direction 1 (reply)");
        assert_eq!(CTINFO2DIR(2), 0, "ctinfo=2    → direction 0");
        assert_eq!(CTINFO2DIR(3), 1, "ctinfo=3    → direction 1");
    }
}
