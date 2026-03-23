/**
 * Cascading Selector - CDP tap helper
 *
 * Env vars:
 *   TAP_STRATEGY: "text" | "testid" | "xpath" | "xpath_contains" | "css" | "placeholder"
 *   TAP_TEXT: primary text to match
 *   FALLBACK_TESTID: fallback data-testid
 *   FALLBACK_XPATH: fallback XPath expression
 *   FALLBACK_POINT_X, FALLBACK_POINT_Y: last-resort coordinates
 *   TAP_CSS: CSS selector (for css strategy)
 *   ACTION: "tap" (default) | "input"
 *   INPUT_VALUE: value to input (when ACTION=input)
 */

const strategy = TAP_STRATEGY || 'text';
const text = TAP_TEXT || '';
const fallbackTestId = FALLBACK_TESTID || '';
const fallbackXpath = FALLBACK_XPATH || '';
const tapCss = TAP_CSS || '';

function findByText(t) {
  const xpath = `//*[contains(text(),'${t}')]`;
  const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
  return result.singleNodeValue;
}

function findByTestId(id) {
  return document.querySelector(`[data-testid="${id}"]`);
}

function findByXpath(expr) {
  const result = document.evaluate(expr, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
  return result.singleNodeValue;
}

function findByCss(sel) {
  return document.querySelector(sel);
}

function findByPlaceholder(ph) {
  return document.querySelector(`[placeholder="${ph}"]`);
}

let element = null;

// Primary strategy
switch (strategy) {
  case 'text':
    element = findByText(text);
    break;
  case 'testid':
    element = findByTestId(text);
    break;
  case 'xpath':
    element = findByXpath(text);
    break;
  case 'xpath_contains':
    element = findByXpath(fallbackXpath || `//*[contains(text(),'${text}')]`);
    break;
  case 'css':
    element = findByCss(tapCss);
    break;
  case 'placeholder':
    element = findByPlaceholder(text);
    break;
}

// Fallback chain
if (!element && fallbackTestId) {
  element = findByTestId(fallbackTestId);
}
if (!element && fallbackXpath) {
  element = findByXpath(fallbackXpath);
}

if (element) {
  if (ACTION === 'input' && INPUT_VALUE) {
    element.focus();
    element.value = INPUT_VALUE;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  } else {
    element.click();
  }
  output.result = 'SUCCESS';
} else {
  output.result = 'ELEMENT_NOT_FOUND';
}
