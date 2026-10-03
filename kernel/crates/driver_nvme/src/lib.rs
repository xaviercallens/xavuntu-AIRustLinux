#![no_std]
#![warn(clippy::pedantic)]
#![deny(clippy::all)]

// Mock requires/ensures macros
macro_rules! requires {
    ($($tt:tt)*) => {};
}

macro_rules! ensures {
    ($($tt:tt)*) => {};
}

/// A zero-cost abstraction for a hardware DMA queue (Submission/Completion).
/// Modulo arithmetic ensures we never overflow.
pub struct SafeDmaQueue<T, const SIZE: usize> {
    /// Raw pointer to the PCIe memory-mapped region for the ring buffer
    ring_ptr: *mut T,
    head: usize,
    tail: usize,
}

impl<T, const SIZE: usize> SafeDmaQueue<T, SIZE> {
    /// Creates a new `SafeDmaQueue` wrapping a raw PCIe pointer.
    ///
    /// # Safety
    /// The caller must ensure `ring_ptr` is valid, properly aligned, and points
    /// to a region of memory large enough to hold `SIZE` elements of `T`.
    pub unsafe fn new(ring_ptr: *mut T) -> Self {
        requires!(SIZE > 0);
        requires!(SIZE.is_power_of_two()); // Commonly DMA queues are powers of 2

        Self {
            ring_ptr,
            head: 0,
            tail: 0,
        }
    }

    /// Pushes an element onto the DMA queue if there is space.
    pub fn push(&mut self, item: T) -> Result<(), &'static str> {
        requires!(self.head < usize::MAX);
        requires!(self.tail < usize::MAX);

        if self.head.wrapping_sub(self.tail) == SIZE {
            return Err("Queue is full");
        }

        let index = self.head % SIZE;
        
        // SAFETY: The bounds are enforced by the modulo `SIZE` operation,
        // preventing Off-By-One memory overflows. `ring_ptr` is guaranteed
        // to have at least `SIZE` elements by the constructor's safety contract.
        unsafe {
            self.ring_ptr.add(index).write_volatile(item);
        }

        self.head = self.head.wrapping_add(1);

        ensures!(self.head.wrapping_sub(self.tail) <= SIZE);
        Ok(())
    }

    /// Pops an element from the DMA queue if one is available.
    pub fn pop(&mut self) -> Option<T> {
        requires!(self.head < usize::MAX);
        requires!(self.tail < usize::MAX);

        if self.head == self.tail {
            return None;
        }

        let index = self.tail % SIZE;

        // SAFETY: The bounds are enforced by the modulo `SIZE` operation,
        // preventing Off-By-One memory overflows. `ring_ptr` is guaranteed
        // to have at least `SIZE` elements by the constructor's safety contract.
        let item = unsafe {
            self.ring_ptr.add(index).read_volatile()
        };

        self.tail = self.tail.wrapping_add(1);

        ensures!(self.head.wrapping_sub(self.tail) <= SIZE);
        Some(item)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_safe_dma_queue() {
        const SIZE: usize = 4;
        let mut buffer = [0u32; SIZE];
        let ptr = buffer.as_mut_ptr();
        
        let mut queue = unsafe { SafeDmaQueue::<u32, SIZE>::new(ptr) };
        
        // Test pop on empty
        assert_eq!(queue.pop(), None);
        
        // Test push
        assert_eq!(queue.push(10), Ok(()));
        assert_eq!(queue.push(20), Ok(()));
        assert_eq!(queue.push(30), Ok(()));
        assert_eq!(queue.push(40), Ok(()));
        
        // Test full
        assert_eq!(queue.push(50), Err("Queue is full"));
        
        // Test pop
        assert_eq!(queue.pop(), Some(10));
        assert_eq!(queue.pop(), Some(20));
        
        // Push again
        assert_eq!(queue.push(60), Ok(()));
        
        // Pop rest
        assert_eq!(queue.pop(), Some(30));
        assert_eq!(queue.pop(), Some(40));
        assert_eq!(queue.pop(), Some(60));
        assert_eq!(queue.pop(), None);
    }
}
