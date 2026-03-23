// input_text_remote.js
// Maestro runScript → Flask → CDP atomic (find + focus + setValue) 로 WebView에 텍스트 입력
//
// env vars (YAML 상위 env에 선언, 글로벌로 접근):
//   TEXT            - 입력할 텍스트 (필수)
//   TAP_ID          - HTML id로 입력 필드 찾기 (선택, 우선순위 1)
//   TAP_SELECTOR    - CSS selector로 입력 필드 찾기 (선택, 우선순위 2)
//   PLACEHOLDER     - placeholder로 입력 필드 찾기 (선택, 우선순위 3)
//   APP_ID          - 앱 패키지명 (기본: com.alphaz.app)
//   DEVICE          - ADB device serial (선택, multi-device 환경용)
//   INPUT_SERVER    - Flask 서버 URL (기본: http://localhost:5100)
//
// TAP_ID/TAP_SELECTOR/PLACEHOLDER 중 하나를 지정하면 별도 tap_remote.js 없이
// 요소 찾기 + 포커스 + 값 설정을 단일 atomic CDP 호출로 수행.

var serverUrl = typeof INPUT_SERVER !== 'undefined' ? INPUT_SERVER : 'http://localhost:5100';
var text = typeof TEXT !== 'undefined' ? TEXT : '';
var tapId = typeof TAP_ID !== 'undefined' ? TAP_ID : '';
var tapSelector = typeof TAP_SELECTOR !== 'undefined' ? TAP_SELECTOR : '';
var placeholder = typeof PLACEHOLDER !== 'undefined' ? PLACEHOLDER : '';
var appId = typeof APP_ID !== 'undefined' ? APP_ID : 'com.alphaz.app';
var device = typeof DEVICE !== 'undefined' ? DEVICE : '';

if (!text) {
    throw new Error('TEXT env var is required');
}

var url = serverUrl + '/cdp-input?text=' + encodeURIComponent(text)
    + '&app_id=' + encodeURIComponent(appId);
if (device) {
    url += '&device=' + encodeURIComponent(device);
}
if (tapId) {
    url += '&target_id=' + encodeURIComponent(tapId);
} else if (tapSelector) {
    url += '&target_selector=' + encodeURIComponent(tapSelector);
} else if (placeholder) {
    url += '&placeholder=' + encodeURIComponent(placeholder);
}
var response = http.get(url);
if (!response.ok) {
    throw new Error('CDP input failed: HTTP ' + response.status + ' ' + response.body);
}

var result = JSON.parse(response.body);
output.success = result.success ? 'true' : 'false';
output.method = result.method || 'cdp';
output.value = result.value || '';
