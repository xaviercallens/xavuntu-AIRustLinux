#![cfg_attr(not(target_arch = "x86_64"), no_std)]


#[cfg(not(target_arch = "x86_64"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
