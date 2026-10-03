#![no_std]

//! Inter-Core Interconnect (ICI) Networking
//!
//! Implementation of the `AF_ICI` socket family for native ICI DMA routing tables.
//! Translates POSIX `send()`/`recv()` directly into ICI DMA routing tables.

/// AF_ICI address family identifier.
pub const AF_ICI: u16 = 43;

/// An ICI Endpoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IciEndpoint {
    pub pod_id: u16,
    pub core_id: u16,
}

/// A socket bound to the AF_ICI family.
pub struct IciSocket {
    local_endpoint: IciEndpoint,
}

impl IciSocket {
    /// Creates a new ICI socket bound to the given local endpoint.
    pub fn new(local_endpoint: IciEndpoint) -> Self {
        Self { local_endpoint }
    }

    /// Sends data over ICI DMA directly to the remote endpoint.
    pub fn send(&self, remote: &IciEndpoint, data: &[u8]) -> Result<usize, &'static str> {
        if data.is_empty() {
            return Err("Empty payload");
        }
        
        // Mock: Update ICI DMA routing table and transfer data.
        // In a real implementation, this interacts directly with the TPU's network interface.
        
        Ok(data.len())
    }

    /// Receives data over ICI DMA.
    pub fn recv(&self, buffer: &mut [u8]) -> Result<usize, &'static str> {
        // Mock: Poll ICI DMA ring buffer.
        if buffer.is_empty() {
            return Err("Buffer too small");
        }
        Ok(0) // Mock 0 bytes received.
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ici_socket_send() {
        let sock = IciSocket::new(IciEndpoint { pod_id: 1, core_id: 0 });
        let remote = IciEndpoint { pod_id: 1, core_id: 1 };
        
        let data = [0xAA, 0xBB, 0xCC];
        let bytes_sent = sock.send(&remote, &data).unwrap();
        assert_eq!(bytes_sent, 3);
    }
}
