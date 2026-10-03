use std::env;
use std::time::Instant;

#[repr(C)]
struct FibNode {
    key: u32,
    value: i32,
    left: *mut FibNode,
    right: *mut FibNode,
}

fn create_node(key: u32, value: i32) -> *mut FibNode {
    Box::into_raw(Box::new(FibNode {
        key,
        value,
        left: std::ptr::null_mut(),
        right: std::ptr::null_mut(),
    }))
}

fn lookup_route(mut root: *mut FibNode, key: u32) -> i32 {
    unsafe {
        while !root.is_null() {
            if key == (*root).key {
                return (*root).value;
            }
            root = if key < (*root).key {
                (*root).left
            } else {
                (*root).right
            };
        }
    }
    -1
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    unsafe {
        let root = create_node(50, 1);
        (*root).left = create_node(25, 2);
        (*root).right = create_node(75, 3);
        (*(*root).left).left = create_node(10, 4);
        (*(*root).left).right = create_node(40, 5);

        let start = Instant::now();

        for _ in 0..iterations {
            lookup_route(root, 40);
        }

        let elapsed = start.elapsed();
        println!("{:.9}", elapsed.as_secs_f64());
    }
}
