// tap_remote.js
// Maestro runScript → Flask → CDP element.click()으로 WebView 버튼 탭
//
// maestro-runner의 DeviceLab 드라이버가 WebView 탭을 전달하지 못하는 문제 우회.
//
// env vars (YAML env에 선언):
//   TAP_ID          - HTML id 속성 (예: profile-insert.click-btn-5)
//   TAP_TEXT        - 버튼 텍스트로 찾기 (id 없을 때)
//   TAP_SELECTOR    - CSS selector로 찾기 (가장 유연)
//   APP_ID          - 앱 패키지명 (기본: com.alphaz.app)
//   DEVICE          - ADB device serial (선택, multi-device 환경용)
//   POLL_TIMEOUT    - 요소 탐색 타임아웃 초 (기본: 15, 시나리오 실행 시 30 권장)
//   INPUT_SERVER    - Flask 서버 URL (기본: http://localhost:5100)
//
// 우선순위: TAP_ID > TAP_SELECTOR > TAP_TEXT

var serverUrl = typeof INPUT_SERVER !== 'undefined' ? INPUT_SERVER : 'http://localhost:5100';
var tapId = typeof TAP_ID !== 'undefined' ? TAP_ID : '';
var tapText = typeof TAP_TEXT !== 'undefined' ? TAP_TEXT : '';
var tapSelector = typeof TAP_SELECTOR !== 'undefined' ? TAP_SELECTOR : '';
var appId = typeof APP_ID !== 'undefined' ? APP_ID : 'com.alphaz.app';
var device = typeof DEVICE !== 'undefined' ? DEVICE : '';
var pollTimeout = typeof POLL_TIMEOUT !== 'undefined' ? POLL_TIMEOUT : '';

if (!tapId && !tapText && !tapSelector) {
    throw new Error('TAP_ID, TAP_TEXT, or TAP_SELECTOR env var is required');
}

var url = serverUrl + '/cdp-tap?app_id=' + encodeURIComponent(appId);
if (device) {
    url += '&device=' + encodeURIComponent(device);
}
if (pollTimeout) {
    url += '&poll_timeout=' + encodeURIComponent(pollTimeout);
}
if (tapId) {
    url += '&id=' + encodeURIComponent(tapId);
} else if (tapSelector) {
    url += '&selector=' + encodeURIComponent(tapSelector);
} else {
    url += '&text=' + encodeURIComponent(tapText);
}

var response = http.get(url);
if (!response.ok) {
    throw new Error('CDP tap failed: HTTP ' + response.status + ' ' + response.body);
}

var result = JSON.parse(response.body);
output.success = result.success ? 'true' : 'false';
output.method = result.method || 'cdp';
