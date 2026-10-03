pub struct SafeSock<'a> {
    ptr: *mut sock,
    _marker: core::marker::PhantomData<&'a mut sock>,
}

impl<'a> SafeSock<'a> {
    pub unsafe fn new(ptr: *mut sock) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }

    pub fn tcp_inet6_sk(&self) -> Option<*mut ipv6_pinfo> {
        let offset = core::mem::size_of::<sock>() - core::mem::size_of::<ipv6_pinfo>();
        // SAFETY: The offset calculation is valid for the structure layout
        let ptr = self.ptr as *mut u8;
        let pinfo = unsafe { ptr.add(offset) as *mut ipv6_pinfo };
        if pinfo.is_null() { None } else { Some(pinfo) }
    }
}

pub struct SafeSkb<'a> {
    ptr: *const sk_buff,
    _marker: core::marker::PhantomData<&'a sk_buff>,
}

impl<'a> SafeSkb<'a> {
    pub unsafe fn new(ptr: *const sk_buff) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }

    pub fn dst(&self) -> Option<*mut c_void> {
        let dst_ptr = unsafe { skb_dst(self.ptr) };
        if dst_ptr.is_null() { None } else { Some(dst_ptr) }
    }

    pub fn ipv6_hdr(&self) -> ipv6hdr {
        unsafe { skb_ipv6_hdr(self.ptr) }
    }

    pub fn tcp_hdr(&self) -> tcphdr {
        unsafe { skb_tcp_hdr(self.ptr) }
    }
}

