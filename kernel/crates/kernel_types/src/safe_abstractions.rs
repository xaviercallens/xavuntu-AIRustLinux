pub struct SafeSock<'a> {
    pub ptr: *mut crate::sock,
    _marker: core::marker::PhantomData<&'a mut crate::sock>,
}

impl<'a> SafeSock<'a> {
    pub unsafe fn new(ptr: *mut crate::sock) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeSkb<'a> {
    pub ptr: *const crate::sk_buff,
    _marker: core::marker::PhantomData<&'a crate::sk_buff>,
}

impl<'a> SafeSkb<'a> {
    pub unsafe fn new(ptr: *const crate::sk_buff) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}

pub struct SafeSkbMut<'a> {
    pub ptr: *mut crate::sk_buff,
    _marker: core::marker::PhantomData<&'a mut crate::sk_buff>,
}

impl<'a> SafeSkbMut<'a> {
    pub unsafe fn new(ptr: *mut crate::sk_buff) -> Option<Self> {
        if ptr.is_null() { None } else { Some(Self { ptr, _marker: core::marker::PhantomData }) }
    }
}
