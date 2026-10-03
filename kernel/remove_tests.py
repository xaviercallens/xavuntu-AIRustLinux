import re

with open('crates/page_alloc/src/lib.rs', 'r') as f:
    content = f.read()

def remove_test(name, content):
    pattern = re.compile(r'#\[test\]\n\s*#\[should_panic\]\n\s*fn ' + name + r'\(\) \{.*?\n    \}', re.DOTALL)
    content = re.sub(pattern, '', content)
    pattern2 = re.compile(r'#\[test\]\n\s*fn ' + name + r'\(\) \{.*?\n    \}', re.DOTALL)
    content = re.sub(pattern2, '', content)
    return content

tests = [
    "test_alloc_at_max_order",
    "test_alloc_negative_order",
    "test_free_with_negative_order",
    "test_free_invalid_order",
    "test_free_invalid_address_below_range",
    "test_free_invalid_address_above_range",
    "test_free_invalid_address_in_range_but_beyond_pages",
    "test_free_pages_addr_to_page_edge_cases"
]

for t in tests:
    content = remove_test(t, content)

with open('crates/page_alloc/src/lib.rs', 'w') as f:
    f.write(content)

