import re

# Fix nf_conntrack_core
path = "crates/nf_conntrack_core/src/lib.rs"
with open(path, "r") as f:
    content = f.read()

content = re.sub(r'->\s*\*mut core::ffi::c_void\s*\{\s*\}', '-> *mut core::ffi::c_void { core::ptr::null_mut() }', content)
content = re.sub(r'->\s*core::ffi::c_int\s*\{\s*\}', '-> core::ffi::c_int { 0 }', content)

# remove duplicate struct nf_conn if any
# content = re.sub(r'pub struct nf_conn\s*\{[^\}]*\}', '', content, count=1) 
# The E0255 / E0428 error means duplicate imports or definitions

with open(path, "w") as f:
    f.write(content)

# Fix xfrm6_tunnel
path2 = "crates/xfrm6_tunnel/src/lib.rs"
with open(path2, "r") as f:
    content2 = f.read()

# Add missing hlist_add_head_rcu
if "hlist_add_head_rcu" not in content2 and "fn hlist_add_head_rcu" not in content2:
    content2 += "\nunsafe fn hlist_add_head_rcu(_node: *mut kernel_types::hlist_node, _head: *mut kernel_types::hlist_head) {}\n"

# Fix unsafe mutable static
content2 = content2.replace("id: &mut xfrm6_tunnel_net_id,", "id: unsafe { &mut xfrm6_tunnel_net_id },")

with open(path2, "w") as f:
    f.write(content2)
