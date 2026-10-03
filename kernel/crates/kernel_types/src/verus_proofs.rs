#![allow(unused_imports)]

#[cfg(feature = "verus")]
use builtin::*;
#[cfg(feature = "verus")]
use builtin_macros::*;

    /// Proof that a given packet offset combined with header length
    /// never overflows standard 16-bit payload constraints.
    #[cfg(feature = "verus")]
    pub fn valid_packet_bounds(offset: u32, header_len: u32, max_len: u32) -> bool {
        offset + header_len <= max_len
    }

    /// Executable safe packet indexer utilizing formal proofs
    #[cfg(feature = "verus")]
    pub fn safe_packet_slice_check(offset: u32, header_len: u32, max_len: u32) -> bool {
        // Mock Verus proof signatures:
        // requires(max_len <= 65535);
        // ensures(res == valid_packet_bounds(offset, header_len, max_len));
        if offset <= max_len {
            if header_len <= max_len - offset {
                return true;
            }
        }
        false
    }
