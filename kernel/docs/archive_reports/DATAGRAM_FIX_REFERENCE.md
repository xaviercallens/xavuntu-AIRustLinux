# datagram Module Fix Reference Card

**Quick Reference for v9.1.0 Implementation**

---

## 📊 At a Glance

| Aspect | Details |
|--------|---------|
| **Module** | datagram |
| **Errors** | 23 |
| **Risk** | HIGH |
| **Complexity** | Very Hard |
| **Effort** | 30-45 min code + testing |
| **Impact** | Requires kernel_types changes |
| **Target** | v9.1.0 (4 weeks) |

---

## 🔧 Required Changes

### 1. kernel_types::sock (+4 fields)

```rust
// Location: crates/kernel_types/src/lib.rs

#[repr(C)]
#[derive(Copy, Clone)]
pub struct sock {
    // ... existing fields ...
    
    // ADD:
    pub sk_prot: *mut proto,      // Protocol ops (4 uses in datagram)
    pub sk_mark: __u32,            // Socket mark (1 use)
    pub sk_uid: kuid_t,            // Owner UID (1 use)
    pub sk_v6_daddr: in6_addr,     // IPv6 dest (2 uses)
}

// Supporting types needed:
#[repr(C)]
pub struct proto {
    _private: [u8; 0],
}

pub type kuid_t = __u32;
```

### 2. kernel_types::dst_entry (+2 fields)

```rust
// Location: crates/kernel_types/src/lib.rs

#[repr(C)]
#[derive(Copy, Clone)]
pub struct dst_entry {
    // ... existing fields ...
    
    // ADD:
    pub obsolete: c_int,           // Obsolete flag (1 use)
    pub ops: *mut dst_ops,         // Operations (1 use)
}

// dst_ops should already exist, verify definition
```

### 3. RCU Functions (+3 functions)

```rust
// Location: crates/kernel_types/src/lib.rs

extern "C" {
    // ADD:
    pub fn rcu_read_lock();        // RCU lock (1 use)
    pub fn rcu_read_unlock();      // RCU unlock (2 uses)
}
```

### 4. datagram Variables (+2 fixes)

```rust
// Location: crates/datagram/src/lib.rs

// Fix undefined variables:
// - inet (1 use): Extract from sk or add parameter
// - np (1 use): Extract from sk or add parameter

// Likely pattern:
let inet = get_inet_sock(sk);  // Add helper
let np = get_ipv6_pinfo(sk);   // Add helper
```

### 5. Type Mismatches (+1 fix)

```rust
// Run: cargo check -p datagram
// Then fix based on specific error message
```

---

## ⚠️ Risk Assessment

### HIGH RISK Areas:

**1. Breaking 296 Working Modules**
- Modifying kernel_types affects ALL modules
- Each field addition could cause cascades
- Must test after each change

**2. ABI Compatibility**
- Struct layout must match Linux kernel exactly
- Wrong offsets break FFI at runtime
- Need verification tools

**3. Field Semantics**
- Fields must have correct types
- Pointers must have correct semantics
- Safety invariants must be documented

---

## ✅ Testing Checklist

After each change:

```bash
# 1. Check datagram
cargo check -p datagram

# 2. Check workspace
cargo build --workspace 2>&1 | tee test.log

# 3. Count successes
grep "Compiling" test.log | wc -l
# Should be: 297

# 4. Check for errors
grep "^error\[" test.log | wc -l
# Should be: 0

# 5. Verify critical modules
cargo check -p netfilter
cargo check -p af_inet6
cargo check -p udp
cargo check -p tcp
```

---

## 📋 Implementation Order

### Recommended Sequence:

**Week 1: Setup**
1. Create branch: `feature/kernel-types-v9.1.0`
2. Set up test automation
3. Document current state
4. Create rollback plan

**Week 2: Add Fields**
1. Add sock::sk_prot → Test
2. Add sock::sk_mark → Test
3. Add sock::sk_uid → Test
4. Add sock::sk_v6_daddr → Test
5. Add dst_entry::obsolete → Test
6. Add dst_entry::ops → Test
7. Full regression test

**Week 3: Add Functions & Fix Variables**
1. Add RCU functions → Test
2. Fix inet variable → Test
3. Fix np variable → Test
4. Fix type mismatches → Test
5. Verify datagram compiles

**Week 4: Final Validation**
1. Full workspace test
2. ABI verification
3. Documentation
4. Release v9.1.0

---

## 🔍 Error Reference

### Current Errors (from cargo check -p datagram):

```
error[E0609]: no field `sk_prot` on type `kernel_types::sock`
   --> crates/datagram/src/lib.rs:XXX:XX
    (4 occurrences)

error[E0609]: no field `sk_mark` on type `kernel_types::sock`
    (1 occurrence)

error[E0609]: no field `sk_uid` on type `kernel_types::sock`
    (1 occurrence)

error[E0609]: no field `sk_v6_daddr` on type `kernel_types::sock`
    (2 occurrences)

error[E0609]: no field `obsolete` on type `*mut kernel_types::dst_entry`
    (1 occurrence)

error[E0609]: no field `ops` on type `*mut kernel_types::dst_entry`
    (1 occurrence)

error[E0425]: cannot find function `rcu_read_lock` in this scope
    (1 occurrence)

error[E0425]: cannot find function `rcu_read_unlock` in this scope
    (2 occurrences)

error[E0425]: cannot find value `inet` in this scope
    (1 occurrence)

error[E0425]: cannot find value `np` in this scope
    (1 occurrence)

error[E0308]: mismatched types
    (5+ occurrences - need individual analysis)
```

---

## 🚨 Rollback Procedure

If anything breaks:

```bash
# 1. Stop immediately
# 2. Document what broke
# 3. Revert changes
git checkout main

# 4. Delete feature branch (optional)
git branch -D feature/kernel-types-v9.1.0

# 5. Analyze and adjust plan
# 6. Try alternative approach
```

---

## 📞 When to Escalate

**Stop and escalate if:**
- Regression in >5 modules
- ABI verification fails
- Unknown error patterns appear
- Timeline significantly delayed
- Critical module breaks

---

## 🎯 Success Criteria

### Must Achieve:
- ✅ datagram compiles (0 errors)
- ✅ All 297 modules compile
- ✅ Zero regressions
- ✅ ABI compatibility maintained

### Definition of Done:
```bash
cargo build --workspace 2>&1 | grep "^error\[" | wc -l
# Output: 0

cargo build --workspace 2>&1 | grep "Compiling" | wc -l  
# Output: 297
```

---

## 📚 Reference Documents

- **Full Plan:** [V9_1_0_ROADMAP.md](./V9_1_0_ROADMAP.md)
- **Current Status:** [ROADMAP_SUMMARY.md](./ROADMAP_SUMMARY.md)
- **Fix Patterns:** [PERFECT_100_PERCENT_REPORT.md](./PERFECT_100_PERCENT_REPORT.md)

---

## 💡 Quick Tips

1. **Test after every single change** - Don't batch changes
2. **Keep commits small** - Easy to revert
3. **Document assumptions** - Helps debugging
4. **Verify ABI** - Use verification tools
5. **Watch for cascades** - One change can affect many modules
6. **Trust the process** - Follow the plan
7. **Ask for help** - Better to escalate early

---

## 🎓 Key Learnings from v9.0.0

These patterns were successful in fixing 16 modules:

1. Incremental changes with testing
2. Conservative, minimal fixes
3. No infrastructure changes
4. Self-contained solutions
5. Documentation at every step

**For v9.1.0, we're deliberately taking infrastructure risk because:**
- It's the last module (1/297)
- Infrastructure update is necessary
- Benefits outweigh risks
- We have proper planning and testing

---

*Keep this reference handy during v9.1.0 implementation!*  
*Last Updated: May 20, 2026*
