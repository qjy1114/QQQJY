// ---- DOM refs ----
var rawTextInput = document.getElementById('rawText');
var usernameInput = document.getElementById('username');
var passwordInput = document.getElementById('password');
var captchaInput = document.getElementById('captcha');
var targetUrlInput = document.getElementById('targetUrl');
var parseButton = document.getElementById('parseButton');
var fillButton = document.getElementById('fillButton');
var clearButton = document.getElementById('clearButton');
var parseResult = document.getElementById('parseResult');
var fillLog = document.getElementById('fillLog');

var modeStandard = document.getElementById('modeStandard');
var modeCdp = document.getElementById('modeCdp');
var standardFields = document.getElementById('standardFields');
var cdpFields = document.getElementById('cdpFields');
var cdpUrlInput = document.getElementById('cdpUrlInput');
var targetUrlCdp = document.getElementById('targetUrlCdp');

// ---- Helpers ----

function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value);
  }
}

function appendLog(message, isError) {
  var line = document.createElement('div');
  line.textContent = message;
  line.style.marginBottom = '8px';
  if (isError) {
    line.style.color = '#b91c1c';
  }
  fillLog.appendChild(line);
  fillLog.scrollTop = fillLog.scrollHeight;
}

function isCdpMode() {
  return modeCdp.checked;
}

// ---- Mode toggle ----

function updateModeUI() {
  var cdp = isCdpMode();
  standardFields.style.display = cdp ? 'none' : 'block';
  cdpFields.style.display = cdp ? 'block' : 'none';
}

modeStandard.addEventListener('change', updateModeUI);
modeCdp.addEventListener('change', updateModeUI);

// ---- Parse ----

async function parseData() {
  var rawText = rawTextInput.value.trim();
  if (!rawText) {
    parseResult.textContent = '请先粘贴原始数据。';
    return;
  }

  try {
    var resp = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rawText: rawText }),
    });
    var data = await resp.json();
    if (!resp.ok) {
      parseResult.textContent = data.error || '解析失败';
      return;
    }
    parseResult.textContent = formatJson(data.rows);
    appendLog('解析成功，找到 ' + data.count + ' 条记录。');
  } catch (err) {
    parseResult.textContent = '解析请求失败：' + err.message;
  }
}

// ---- Fill ----

async function fillData() {
  var rawText = rawTextInput.value.trim();
  if (!rawText) {
    alert('请先粘贴原始数据。');
    return;
  }

  fillLog.textContent = '';
  appendLog('开始自动填表，请稍候...');

  var payload = { rawText: rawText };

  if (isCdpMode()) {
    // CDP mode: connect to existing browser
    payload.attach = true;
    payload.cdpUrl = cdpUrlInput.value.trim() || 'http://127.0.0.1:9222';
    payload.targetUrl = targetUrlCdp.value.trim() || 'http://36.212.5.102:30869/#/order/order/submit';
  } else {
    // Standard mode: login with credentials
    var username = usernameInput.value.trim();
    var password = passwordInput.value.trim();
    var captcha = captchaInput.value.trim();
    var targetUrl = targetUrlInput.value.trim();

    if (!username || !password || captcha === '') {
      alert('请补全用户名、密码和验证码。');
      return;
    }
    payload.username = username;
    payload.password = password;
    payload.captcha = captcha;
    payload.targetUrl = targetUrl || 'http://36.212.5.102:30869/#/order/order/submit';
  }

  try {
    var resp = await fetch('/api/fill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    var data = await resp.json();
    if (!resp.ok) {
      appendLog('自动填表失败：' + (data.error || '未知错误'), true);
      return;
    }
    if (Array.isArray(data.results)) {
      data.results.forEach(function (result) {
        if (result.success) {
          appendLog('第 ' + result.line + ' 行 ' + result.enterprise + '：保存成功');
        } else {
          appendLog('第 ' + result.line + ' 行 ' + result.enterprise + '：失败 - ' + result.error, true);
        }
      });
    } else {
      appendLog('自动填表完成，但未返回结果详情。');
    }
  } catch (err) {
    appendLog('自动填表请求失败：' + err.message, true);
  }
}

// ---- Event binding ----

parseButton.addEventListener('click', parseData);
fillButton.addEventListener('click', fillData);
clearButton.addEventListener('click', function () {
  parseResult.textContent = '解析结果会显示在这里。';
  fillLog.textContent = '自动填表日志会显示在这里。';
});
