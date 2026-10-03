#[repr(C)]
   pub struct in6_addr {
       pub s6_addr: [u8; 16],
   }

   impl in6_addr {
       pub fn from_ipv6(addr: std::net::Ipv6Addr) -> Self {
           let bytes = addr.octets();
           in6_addr { s6_addr: bytes }
       }
   }