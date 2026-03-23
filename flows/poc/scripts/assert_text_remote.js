/**
 * Cascading Selector - CDP assertion helper
 *
 * Env vars:
 *   ASSERT_STRATEGY: "contains" | "regex" | "element_exists"
 *   ASSERT_TEXT: text to search for (contains strategy)
 *   ASSERT_PATTERN: regex pattern (regex strategy)
 *   ASSERT_CONTAINER: CSS selector for container scope
 *   ASSERT_CSS: CSS selector (element_exists strategy)
 *   EXPECTED: "true" | "false"
 */

const strategy = ASSERT_STRATEGY || 'contains';
const expected = EXPECTED === 'true';
let found = false;

switch (strategy) {
  case 'contains': {
    const text = ASSERT_TEXT || '';
    const container = ASSERT_CONTAINER
      ? document.querySelector(ASSERT_CONTAINER)
      : document.body;
    found = container ? container.textContent.includes(text) : false;
    break;
  }
  case 'regex': {
    const pattern = new RegExp(ASSERT_PATTERN || '');
    const container = ASSERT_CONTAINER
      ? document.querySelector(ASSERT_CONTAINER)
      : document.body;
    found = container ? pattern.test(container.textContent) : false;
    break;
  }
  case 'element_exists': {
    const css = ASSERT_CSS || '';
    found = !!document.querySelector(css);
    break;
  }
}

output.result = found === expected ? 'PASS' : 'FAIL';
output.found = found;
output.expected = expected;
