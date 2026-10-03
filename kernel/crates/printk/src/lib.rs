#![allow(clippy::all, clippy::pedantic)]
#![cfg_attr(not(test), no_std)]
//! Kernel logging - Phase 1: Serial port output via QEMU

#[allow(non_camel_case_types)]
type c_int = i32;

#[cfg(not(test))]
extern "C" {
    fn x86_out8(port: u16, value: u8);
    fn x86_in8(port: u16) -> u8;
}

#[cfg(test)]
use self::tests::{x86_in8, x86_out8};

const SERIAL_PORT: u16 = 0x3F8;

#[inline]
unsafe fn serial_write_byte(byte: u8) {
    while (x86_in8(SERIAL_PORT + 5) & 0x20) == 0 {}
    x86_out8(SERIAL_PORT, byte);
}

/// Write a string to the serial port.
///
/// # Safety
///
/// - `s` must be a valid pointer to a buffer of at least `len` bytes
/// - The buffer must remain valid for the duration of this call
/// - `len` must accurately represent the buffer size
#[no_mangle]
pub unsafe extern "C" fn printk_str(s: *const u8, len: usize) {
    if !s.is_null() && len > 0 {
        core::slice::from_raw_parts(s, len).iter().for_each(|&b| serial_write_byte(b));
    }
}

/// Write a null-terminated C string to the serial port.
///
/// # Safety
///
/// - `s` must be a valid pointer to a null-terminated string
/// - The string must remain valid for the duration of this call
/// - The string must contain a null terminator within accessible memory
#[no_mangle]
pub unsafe extern "C" fn printk_cstr(s: *const u8) {
    if !s.is_null() {
        let mut p = s;
        while *p != 0 { serial_write_byte(*p); p = p.add(1); }
    }
}

/// Initialize the serial port (COM1 at 0x3F8).
///
/// Configures the 16550 UART with:
/// - 9600 baud (divisor 0x000C)
/// - 8 data bits, no parity, 1 stop bit (8N1)
/// - FIFO enabled
///
/// # Safety
///
/// - Must be called before any printk operations
/// - Uses x86 port I/O which is inherently unsafe
/// - Assumes serial port hardware is present at 0x3F8
#[no_mangle]
pub unsafe extern "C" fn printk_init() -> c_int {
    x86_out8(SERIAL_PORT + 1, 0x00);
    x86_out8(SERIAL_PORT + 3, 0x80);
    x86_out8(SERIAL_PORT, 0x0C);
    x86_out8(SERIAL_PORT + 1, 0x00);
    x86_out8(SERIAL_PORT + 3, 0x03);
    x86_out8(SERIAL_PORT + 2, 0xC7);
    x86_out8(SERIAL_PORT + 4, 0x0B);
    0
}

/// Cleanup function for printk subsystem.
///
/// # Safety
///
/// - Currently a no-op, safe to call at any time
#[no_mangle]
pub unsafe extern "C" fn printk_exit() {}

pub static PRINTK_INITIALIZED: core::sync::atomic::AtomicBool = core::sync::atomic::AtomicBool::new(false);

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Mock storage for port I/O operations
    static MOCK_STATE: Mutex<MockState> = Mutex::new(MockState::new());

    #[derive(Debug)]
    struct MockState { out_calls: Vec<(u16, u8)>, in_value: u8 }

    impl MockState {
        const fn new() -> Self {
            Self {
                out_calls: Vec::new(),
                in_value: 0x20, // TX ready by default
            }
        }

        fn reset(&mut self) {
            self.out_calls.clear();
            self.in_value = 0x20;
        }

        fn set_in_value(&mut self, val: u8) {
            self.in_value = val;
        }

        fn record_out(&mut self, port: u16, value: u8) {
            self.out_calls.push((port, value));
        }

        fn get_out_calls(&self) -> &[(u16, u8)] {
            &self.out_calls
        }
    }

    // Mock implementations for x86 port I/O
    #[no_mangle]
    pub unsafe extern "C" fn x86_out8(port: u16, value: u8) {
        MOCK_STATE.lock().unwrap().record_out(port, value);
    }

    #[no_mangle]
    pub unsafe extern "C" fn x86_in8(_port: u16) -> u8 {
        MOCK_STATE.lock().unwrap().in_value
    }

    #[test]
    fn test_printk_init_success() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            let result = printk_init();
            assert_eq!(result, 0, "printk_init should return 0");
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();
        assert_eq!(calls.len(), 7, "Should have 7 port I/O operations");

        // Verify serial port initialization sequence
        assert_eq!(calls[0], (SERIAL_PORT + 1, 0x00), "Disable interrupts");
        assert_eq!(calls[1], (SERIAL_PORT + 3, 0x80), "Set DLAB");
        assert_eq!(calls[2], (SERIAL_PORT, 0x0C), "Set baud divisor low");
        assert_eq!(calls[3], (SERIAL_PORT + 1, 0x00), "Set baud divisor high");
        assert_eq!(calls[4], (SERIAL_PORT + 3, 0x03), "8N1 mode");
        assert_eq!(calls[5], (SERIAL_PORT + 2, 0xC7), "Enable FIFO");
        assert_eq!(calls[6], (SERIAL_PORT + 4, 0x0B), "Enable DTR/RTS");
    }

    #[test]
    fn test_printk_str_null_pointer() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_str(core::ptr::null(), 100);
        }

        let state = MOCK_STATE.lock().unwrap();
        assert_eq!(state.get_out_calls().len(), 0, "Should not write for null pointer");
    }

    #[test]
    fn test_printk_str_zero_length() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"test";
        unsafe {
            printk_str(msg.as_ptr(), 0);
        }

        let state = MOCK_STATE.lock().unwrap();
        assert_eq!(state.get_out_calls().len(), 0, "Should not write for zero length");
    }

    #[test]
    fn test_printk_str_valid() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Hi";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();

        // Each character requires checking ready status then writing
        // Due to the polling loop, we only see the writes
        let writes: Vec<u8> = calls.iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();

        assert_eq!(writes, vec![b'H', b'i'], "Should write 'Hi'");
    }

    #[test]
    fn test_printk_str_long_message() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Hello, World!";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();

        let writes: Vec<u8> = calls.iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();

        assert_eq!(writes, msg.to_vec(), "Should write entire message");
    }

    #[test]
    fn test_printk_cstr_null_pointer() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_cstr(core::ptr::null());
        }

        let state = MOCK_STATE.lock().unwrap();
        assert_eq!(state.get_out_calls().len(), 0, "Should not write for null pointer");
    }

    #[test]
    fn test_printk_cstr_empty() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"\0";
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        assert_eq!(state.get_out_calls().len(), 0, "Should not write for empty string");
    }

    #[test]
    fn test_printk_cstr_valid() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Test\0";
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();

        let writes: Vec<u8> = calls.iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();

        assert_eq!(writes, b"Test".to_vec(), "Should write 'Test' without null terminator");
    }

    #[test]
    fn test_printk_cstr_with_newline() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Line1\nLine2\0";
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();

        let writes: Vec<u8> = calls.iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();

        assert_eq!(writes, b"Line1\nLine2".to_vec(), "Should write multiline correctly");
    }

    #[test]
    fn test_printk_exit_is_safe() {
        unsafe {
            printk_exit(); // Should not panic
        }
    }

    #[test]
    fn test_serial_port_constant() {
        assert_eq!(SERIAL_PORT, 0x3F8, "COM1 port address");
    }

    #[test]
    fn test_printk_initialized_flag() {
        // Test that the flag exists and can be accessed
        let initial = PRINTK_INITIALIZED.load(core::sync::atomic::Ordering::SeqCst);
        PRINTK_INITIALIZED.store(true, core::sync::atomic::Ordering::SeqCst);
        assert!(PRINTK_INITIALIZED.load(core::sync::atomic::Ordering::SeqCst));
        PRINTK_INITIALIZED.store(initial, core::sync::atomic::Ordering::SeqCst); // Restore
    }

    // === Additional stress and edge case tests ===

    #[test]
    fn test_printk_str_single_byte() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"X";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, vec![b'X']);
    }

    #[test]
    fn test_printk_str_special_characters() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"\n\r\t\0";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, msg.to_vec());
    }

    #[test]
    fn test_printk_str_max_length() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = vec![b'A'; 1024];
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes.len(), 1024);
    }

    #[test]
    fn test_printk_str_binary_data() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg: [u8; 4] = [0xFF, 0x00, 0xAA, 0x55];
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, msg.to_vec());
    }

    #[test]
    fn test_printk_cstr_long_string() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let mut msg = vec![b'B'; 512];
        msg.push(0);
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes.len(), 512);
    }

    #[test]
    fn test_printk_cstr_single_char() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Z\0";
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, vec![b'Z']);
    }

    #[test]
    fn test_printk_multiple_init_calls() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_init();
            printk_init();
            printk_init();
        }

        let state = MOCK_STATE.lock().unwrap();
        // Each init should perform 7 port I/O operations
        assert_eq!(state.get_out_calls().len(), 21);
    }

    #[test]
    fn test_serial_write_sequence() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_str(b"A".as_ptr(), 1);
            printk_str(b"B".as_ptr(), 1);
            printk_str(b"C".as_ptr(), 1);
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, vec![b'A', b'B', b'C']);
    }

    #[test]
    fn test_printk_str_consecutive_calls() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        for _ in 0..10 {
            unsafe {
                printk_str(b"T".as_ptr(), 1);
            }
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes.len(), 10);
    }

    #[test]
    fn test_printk_cstr_consecutive_calls() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        for _ in 0..10 {
            unsafe {
                printk_cstr(b"X\0".as_ptr());
            }
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes.len(), 10);
    }

    #[test]
    fn test_printk_mixed_calls() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_str(b"str1".as_ptr(), 4);
            printk_cstr(b"cstr1\0".as_ptr());
            printk_str(b"str2".as_ptr(), 4);
            printk_cstr(b"cstr2\0".as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, b"str1cstr1str2cstr2".to_vec());
    }

    #[test]
    fn test_printk_exit_multiple_calls() {
        unsafe {
            printk_exit();
            printk_exit();
            printk_exit();
        }
    }

    #[test]
    fn test_printk_str_with_length_one() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"test";
        unsafe {
            printk_str(msg.as_ptr(), 1);
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, vec![b't']);
    }

    #[test]
    fn test_printk_str_numeric_content() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"0123456789";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, msg.to_vec());
    }

    #[test]
    fn test_printk_str_unicode_utf8_bytes() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = "Hello🦀".as_bytes();
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, msg.to_vec());
    }

    #[test]
    fn test_printk_cstr_with_spaces() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"Hello World From Kernel\0";
        unsafe {
            printk_cstr(msg.as_ptr());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, b"Hello World From Kernel".to_vec());
    }

    #[test]
    fn test_printk_init_port_sequence() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        unsafe {
            printk_init();
        }

        let state = MOCK_STATE.lock().unwrap();
        let calls = state.get_out_calls();

        // Verify each port write individually
        assert_eq!(calls.len(), 7);
        for (i, call) in calls.iter().enumerate() {
            assert!(call.0 >= SERIAL_PORT && call.0 <= SERIAL_PORT + 5,
                    "Port {} out of range at index {}", call.0, i);
        }
    }

    #[test]
    fn test_printk_str_stress_1000_chars() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = vec![b'X'; 1000];
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes.len(), 1000);
        assert!(writes.iter().all(|&b| b == b'X'));
    }

    #[test]
    fn test_printk_str_alternating_pattern() {
        let mut state = MOCK_STATE.lock().unwrap();
        state.reset();
        drop(state);

        let msg = b"ABABABABAB";
        unsafe {
            printk_str(msg.as_ptr(), msg.len());
        }

        let state = MOCK_STATE.lock().unwrap();
        let writes: Vec<u8> = state.get_out_calls().iter()
            .filter(|(port, _)| *port == SERIAL_PORT)
            .map(|(_, val)| *val)
            .collect();
        assert_eq!(writes, msg.to_vec());
    }
}
