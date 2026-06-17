const tabValidate = document.getElementById('tabValidate');
const tabSubmit = document.getElementById('tabSubmit');
const panelValidate = document.getElementById('panelValidate');
const panelSubmit = document.getElementById('panelSubmit');
const validateRawText = document.getElementById('validateRawText');
const validateParseButton = document.getElementById('validateParseButton');
const validateIp = document.getElementById('validateIp');
const validatePort = document.getElementById('validatePort');
const validateUsername = document.getElementById('validateUsername');
const validatePassword = document.getElementById('validatePassword');
const validateChannel = document.getElementById('validateChannel');
const validateCaptureType = document.getElementById('validateCaptureType');
const validateStream = document.getElementById('validateStream');
const validateStreamRow = document.getElementById('validateStreamRow');
const validateModeDirect = document.getElementById('validateModeDirect');
const validateModeStream = document.getElementById('validateModeStream');
const validateModeNote = document.getElementById('validateModeNote');
const validateButton = document.getElementById('validateButton');
const validateResult = document.getElementById('validateResult');
const validateImage = document.getElementById('validateImage');
const validateInfo = document.getElementById('validateInfo');
const gotoFill = document.getElementById('gotoFill');
const sessionText = document.getElementById('sessionText');
const logoutButton = document.getElementById('logoutButton');
const batchResultsGrid = document.getElementById('batchResultsGrid');
const captureResults = document.getElementById('captureResults');
const ipTestButton = document.getElementById('ipTestButton');
const ipTestResult = document.getElementById('ipTestResult');

function setActiveTab(tab) {
  tabValidate.classList.toggle('active', tab === 'validate');
  tabSubmit.classList.toggle('active', tab === 'submit');
  panelValidate.classList.toggle('active', tab === 'validate');
  panelSubmit.classList.toggle('active', tab === 'submit');
}

function formatJson(value) {
  try { return JSON.stringify(value, null, 2); }
  catch (err) { return String(value); }
}

function setValidateMode(mode) {
  const isStream = mode === 'stream';
  validateStreamRow.style.display = 'block';
  updateCaptureTypeDropdown(mode);
  validateModeNote.textContent = isStream
    ? '流抓模式：除了 ip、port、username、password、channel、captureType，还必须填写 stream。'
    : '直抓模式：必填 ip、port、username、password、channel、captureType，无需 stream。';
}

function clearValidateFields() {
  validateRawText.value = '';
  validateIp.value = '';
  validatePort.value = '';
  validateUsername.value = 'admin';
  validatePassword.value = '';
  validateChannel.value = '1';
  validateCaptureType.value = '';
  validateStream.value = '';
  const options = validateCaptureType.options;
  for (let i = options.length - 1; i >= 0; i--) {
    const val = options[i].value;
    if (val && _allKnownValues().indexOf(val) === -1) {
      validateCaptureType.remove(i);
    }
  }
  validateModeDirect.checked = true;
  validateModeStream.checked = false;
  setValidateMode('direct');
  validateResult.textContent = '点击按钮开始抓图';
  validateResult.style.color = '#475569';
  validateImage.style.display = 'none';
  validateImage.src = '';
  validateInfo.textContent = '';
}

// ---- AI-powered parse & fill ----

var DIRECT_CAPTURE_OPTIONS = [
  { value: 'CAPTURE_SERVICE_HIKVISION_SDK_FILE', label: '海康直抓' },
  { value: 'CAPTURE_SERVICE_DAHUATECH_SDK', label: '大华直抓' },
];

var STREAM_CAPTURE_OPTIONS = [
  { value: 'hikvision_stream', label: '海康流抓' },
  { value: 'dahua_stream', label: '大华流抓' },
  { value: 'huawei_stream', label: '华为流抓' },
  { value: 'uniview_stream', label: '宇视流抓' },
  { value: 'tp_nvr_stream', label: 'tp录像机流抓' },
  { value: 'tp_ipc_stream', label: 'tp摄像头流抓' },
  { value: 'generic_stream', label: '通用流抓' },
  { value: 'ezviz_stream', label: '萤石流抓' },
];

function _allKnownValues() {
  var vals = [];
  DIRECT_CAPTURE_OPTIONS.forEach(function (o) { vals.push(o.value); });
  STREAM_CAPTURE_OPTIONS.forEach(function (o) { vals.push(o.value); });
  return vals;
}

function _isDirectType(val) {
  return val === 'CAPTURE_SERVICE_HIKVISION_SDK_FILE' || val === 'CAPTURE_SERVICE_DAHUATECH_SDK';
}

function updateCaptureTypeDropdown(mode) {
  var sel = validateCaptureType;
  var currentVal = sel.value;
  sel.innerHTML = '<option value="">请选择抓图类型</option>';
  var options = mode === 'stream' ? STREAM_CAPTURE_OPTIONS : DIRECT_CAPTURE_OPTIONS;
  for (var i = 0; i < options.length; i++) {
    var opt = document.createElement('option');
    opt.value = options[i].value;
    opt.textContent = options[i].label;
    sel.appendChild(opt);
  }
  sel.value = currentVal;
}

function _filterPortsByPriority(portStr) {
  if (!portStr) return '';
  var ports = portStr.split(',').map(function (p) { return p.trim(); }).filter(Boolean);
  if (!ports.length) return '';
  var tier1 = ports.filter(function (p) { var n = parseInt(p); return n >= 8000 && n <= 8003; });
  var tier2 = ports.filter(function (p) { var n = parseInt(p); return n >= 37777 && n <= 37779; });
  var tier3 = ports.filter(function (p) { var n = parseInt(p); return n >= 554 && n <= 556; });
  if (tier1.length) return tier1.join(',');
  if (tier2.length) return tier2.join(',');
  if (tier3.length) return tier3.join(',');
  return '';
}

function buildStreamUrl(optPort, optChannel) {
  var ct = validateCaptureType.value;
  var ip = validateIp.value.trim();

  // 处理端口：支持范围（555-558）和逗号分隔（555,556），只取第一个值
  var portRaw = optPort || validatePort.value.trim();
  var port = portRaw;
  if (portRaw.indexOf('-') !== -1) {
    port = portRaw.split('-')[0].trim();
  } else if (portRaw.indexOf(',') !== -1) {
    port = portRaw.split(',')[0].trim();
  }
  if (!port) port = '554';

  var user = encodeURIComponent(validateUsername.value.trim() || 'admin');
  var pass = encodeURIComponent(validatePassword.value.trim() || 'admin');

  // 处理通道：支持范围和逗号分隔，只取第一个值
  var chRaw = optChannel || validateChannel.value.trim();
  var ch = chRaw;
  if (chRaw.indexOf('-') !== -1) {
    ch = chRaw.split('-')[0].trim();
  } else if (chRaw.indexOf(',') !== -1) {
    ch = chRaw.split(',')[0].trim();
  }
  if (!ch) ch = '1';

  if (!ip) return '';
  switch (ct) {
    case 'hikvision_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/Streaming/Channels/' + ch + '01';
    case 'dahua_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/cam/realmonitor?channel=' + ch + '&subtype=0';
    case 'huawei_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + (port && port !== '554' ? ':' + port : '') + '/LiveMedia/ch' + ch + '/Media1';
    case 'uniview_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/unicast/c' + ch + '/s0/live';
    case 'tp_nvr_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/stream1&channe1=' + ch;
    case 'tp_ipc_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/stream1';
    case 'generic_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/stream1';
    case 'ezviz_stream':
      return 'rtsp://' + user + ':' + pass + '@' + ip + ':' + port + '/h264/ch' + ch + '/main/av_stream';
    default:
      return '';
  }
}

function autoUpdateStream() {
  var ct = validateCaptureType.value;
  if (!ct) return;
  if (_isDirectType(ct)) {
    validateStream.value = buildStreamUrl();
  } else {
    validateModeStream.checked = true;
    validateModeDirect.checked = false;
    setValidateMode('stream');
    validateStream.value = buildStreamUrl();
  }
}

function fillValidateFields(parsed) {
  if (!parsed || typeof parsed !== 'object') return;
  if (parsed.ip) validateIp.value = parsed.ip;
  if (parsed.username) validateUsername.value = parsed.username;
  if (parsed.password) validatePassword.value = parsed.password;

  var rawPort = String(parsed.port || '');
  var filteredPort = _filterPortsByPriority(rawPort);
  if (filteredPort) validatePort.value = filteredPort;

  var channelVal = String(parsed.channel || '');
  if (channelVal && filteredPort) {
    var portCount = filteredPort.split(',').filter(Boolean).length;
    var chanCount = channelVal.split(',').filter(Boolean).length;
    if (chanCount > portCount) {
      validatePort.value = filteredPort.split(',')[0];
      validateChannel.value = channelVal;
    } else if (chanCount === portCount && portCount > 1) {
      // 1:1, leave channel at default
    } else {
      validateChannel.value = channelVal;
    }
  }

  var brand = parsed.brand || parsed.captureType || '';
  var msg = 'AI 解析完成';
  if (parsed.name) msg += '：' + parsed.name;
  if (parsed.ip) msg += ' | ip=' + parsed.ip;
  if (brand) msg += ' | 品牌:' + brand;
  if (filteredPort) msg += ' | 端口:' + filteredPort;
  if (parsed.phone) msg += ' | ' + parsed.phone;
  showValidateResult(msg);
}

validateCaptureType.addEventListener('change', autoUpdateStream);
validateIp.addEventListener('input', autoUpdateStream);
validatePort.addEventListener('input', autoUpdateStream);
validateUsername.addEventListener('input', autoUpdateStream);
validatePassword.addEventListener('input', autoUpdateStream);
validateChannel.addEventListener('input', autoUpdateStream);

async function testIpConnectivity() {
  var ip = validateIp.value.trim();
  var port = (validatePort.value.trim().split(',')[0] || '').trim();
  if (!ip) { ipTestResult.textContent = '请先输入 IP'; ipTestResult.style.color = '#b91c1c'; return; }
  if (!port) { ipTestResult.textContent = '请先输入端口'; ipTestResult.style.color = '#b91c1c'; return; }
  ipTestResult.textContent = '检测中...'; ipTestResult.style.color = '#64748b';
  try {
    var resp = await fetch('/api/check_telnet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip: ip, port: port }),
    });
    var data = await resp.json();
    if (!resp.ok) { ipTestResult.textContent = data.error || '检测失败'; ipTestResult.style.color = '#b91c1c'; return; }
    if (data.reachable) {
      ipTestResult.textContent = ip + ':' + port + ' 连通';
      ipTestResult.style.color = '#16a34a';
    } else {
      ipTestResult.textContent = ip + ':' + port + ' 不通';
      ipTestResult.style.color = '#b91c1c';
    }
  } catch (err) {
    ipTestResult.textContent = '检测失败：' + err.message;
    ipTestResult.style.color = '#b91c1c';
  }
}

async function parseValidationPayload() {
  var rawText = validateRawText.value.trim();
  if (!rawText) { showValidateResult('请先粘贴设备信息。', true); return; }
  showValidateResult('正在调用 AI 解析，请稍候...');
  try {
    var resp = await fetch('/api/parse_device_info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rawText: rawText }),
    });
    var data = await resp.json();
    if (!resp.ok) { showValidateResult(data.error || 'AI 解析失败', true); return; }
    fillValidateFields(data);
  } catch (err) {
    showValidateResult('AI 解析请求失败：' + err.message, true);
  }
}

function showValidateResult(message, isError) {
  validateResult.textContent = message;
  validateResult.style.color = isError ? '#b91c1c' : '#0f172a';
}

// ---- Execute (auto-detects single vs batch) ----

function _isRangeValue(val) {
  return val && (val.indexOf('-') !== -1 || val.indexOf(',') !== -1);
}

async function executeValidate() {
  var portRaw = validatePort.value.trim();
  var channelRaw = validateChannel.value.trim();

  var fieldValues = {
    ip: validateIp.value.trim(),
    username: validateUsername.value.trim(),
    password: validatePassword.value.trim(),
    captureType: validateCaptureType.value.trim(),
    stream: validateStream.value.trim(),
  };
  var required = ['ip', 'username', 'password', 'captureType'];
  var missing = required.filter(function (k) { return !fieldValues[k]; });
  if (!portRaw) missing.push('port');
  if (!channelRaw) missing.push('channel');
  if (missing.length) {
    showValidateResult('请补全字段：' + missing.join(', '), true);
    return;
  }

  if (_isRangeValue(portRaw) || _isRangeValue(channelRaw)) {
    return executeBatchValidate(portRaw, channelRaw, fieldValues);
  }

  // ---- Single capture ----
  var ct = fieldValues.captureType;
  var curMode = _isDirectType(ct) ? 'direct' : 'stream';
  var streamUrl = curMode === 'stream' ? buildStreamUrl() : '';

  validateImage.style.display = 'none';
  validateInfo.textContent = '';
  batchResultsGrid.innerHTML = '';
  showValidateResult('正在调用抓图校验接口，请稍候...');

  var payload = {
    ip: fieldValues.ip, port: portRaw,
    username: fieldValues.username, password: fieldValues.password,
    channel: channelRaw, captureType: ct,
    stream: streamUrl, mode: curMode,
  };

  try {
    var resp = await fetch('/api/capture_validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    var data = await resp.json();
    if (!resp.ok) {
      showValidateResult(data.error || '抓图校验调用失败。', true);
      if (data.response) validateInfo.textContent = JSON.stringify(data.response, null, 2);
      return;
    }
    if (data.imageUrl) {
      validateImage.src = data.imageUrl.startsWith('data:image/') || data.imageUrl.startsWith('http')
        ? data.imageUrl : 'data:image/png;base64,' + data.imageUrl;
      validateImage.style.display = 'block';
      validateImage.onload = function () {
        validateInfo.style.fontSize = '0.75rem';
        validateInfo.textContent = portRaw + ' ' + channelRaw + ' ' + this.naturalWidth + '×' + this.naturalHeight;
      };
      showValidateResult('抓图校验请求已完成。');
    } else {
      validateImage.style.display = 'none';
      validateInfo.textContent = data.response
        ? ('返回数据（未提取到图片）：\n' + formatJson(data.response))
        : '接口调用成功，但未返回图片。';
      showValidateResult('抓图校验请求已完成，但未找到图片。', true);
    }
  } catch (err) {
    showValidateResult('请求失败：' + err.message, true);
  }
}

// ---- Batch capture (sequential, stream each result) ----

function parseRange(input) {
  if (!input || !input.trim()) return [];
  var values = [];
  var parts = input.split(',');
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i].trim();
    if (!part) continue;
    if (part.indexOf('-') !== -1) {
      var rangeParts = part.split('-');
      if (rangeParts.length === 2) {
        var start = parseInt(rangeParts[0], 10);
        var end = parseInt(rangeParts[1], 10);
        if (!isNaN(start) && !isNaN(end) && start <= end) {
          for (var j = start; j <= end; j++) { values.push(String(j)); }
          continue;
        }
      }
    }
    values.push(part);
  }
  return values;
}

function appendBatchCard(r) {
  var card = document.createElement('div');
  card.style.cssText =
    'background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:12px; ' +
    'display:flex; flex-direction:column; align-items:center; gap:8px;';

  var label = document.createElement('div');
  label.style.cssText = 'text-align:center; font-weight:700; font-size:0.75rem;';
  label.textContent = r.port + ' ' + r.channel;
  if (!r.success) label.style.color = '#b91c1c';
  card.appendChild(label);

  if (r.success && r.imageUrl) {
    var img = document.createElement('img');
    img.src = r.imageUrl;
    img.alt = 'Port ' + r.port + ' Ch ' + r.channel;
    img.style.cssText =
      'width:100%; max-width:495px; height:auto; border-radius:10px; border:1px solid #cbd5e1; object-fit:contain;';
    img.onload = (function (lbl, port, ch) {
      return function () {
        lbl.textContent = port + ' ' + ch + ' ' + this.naturalWidth + '×' + this.naturalHeight;
      };
    })(label, r.port, r.channel);
    img.onerror = function () {
      this.style.display = 'none';
      var fb = this.nextElementSibling;
      if (fb) fb.style.display = 'block';
    };
    card.appendChild(img);
    var fallback = document.createElement('div');
    fallback.style.cssText = 'display:none; color:#b91c1c; font-size:0.85rem; text-align:center;';
    fallback.textContent = '图片加载失败';
    card.appendChild(fallback);
  } else {
    var errDiv = document.createElement('div');
    errDiv.style.cssText =
      'width:100%; min-height:80px; display:flex; align-items:center; justify-content:center; ' +
      'background:#fef2f2; border-radius:10px; color:#b91c1c; font-size:0.8rem; padding:10px; text-align:center;';
    errDiv.textContent = r.error || '抓图失败';
    card.appendChild(errDiv);
  }
  batchResultsGrid.appendChild(card);
}

async function _doSingleCapture(ip, port, username, password, channel, captureType, streamUrl, mode) {
  try {
    var body = { ip: ip, port: port, username: username, password: password, channel: channel, captureType: captureType, mode: mode };
    if (mode === 'stream' && streamUrl) body.stream = streamUrl;
    var resp = await fetch('/api/capture_validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    var data = await resp.json();
    return {
      port: port, channel: channel,
      success: resp.ok && !!data.imageUrl,
      imageUrl: data.imageUrl || null,
      error: (!resp.ok ? data.error : null) || (data.imageUrl ? null : '未返回图片'),
    };
  } catch (err) {
    return { port: port, channel: channel, success: false, imageUrl: null, error: err.message };
  }
}

async function executeBatchValidate(portRaw, channelRaw, fieldValues) {
  var ports = parseRange(portRaw);
  var channels = parseRange(channelRaw);
  if (!ports.length) { showValidateResult('port 格式无法识别', true); return; }
  if (!channels.length) { showValidateResult('channel 格式无法识别', true); return; }

  var total = ports.length * channels.length;
  validateImage.style.display = 'none';
  validateInfo.textContent = '';
  batchResultsGrid.innerHTML = '';

  var successCount = 0;
  var done = 0;
  var ct = fieldValues.captureType;
  var useStream = !_isDirectType(ct);

  for (var pi = 0; pi < ports.length; pi++) {
    for (var ci = 0; ci < channels.length; ci++) {
      done++;
      var port = ports[pi];
      var channel = channels[ci];
      var label = '端口 ' + port + ' 通道 ' + channel;
      var curMode = useStream ? 'stream' : 'direct';
      var streamUrl = useStream ? buildStreamUrl(port, channel) : '';
      if (useStream) label += ' [流抓]';
      showValidateResult('抓取中 ' + done + '/' + total + '：' + label + '...');

      var r = await _doSingleCapture(fieldValues.ip, port, fieldValues.username,
        fieldValues.password, channel, ct, streamUrl, curMode);

      if (r.success) successCount++;
      appendBatchCard(r);
    }
  }

  showValidateResult('批量抓图完成：' + successCount + ' / ' + total + ' 成功。');
}

async function loadSessionStatus() {
  try {
    const resp = await fetch('/api/session_status');
    const data = await resp.json();
    if (resp.ok) {
      sessionText.textContent = '会话状态：' + (data.logged_in ? '已登录，用户 ' + data.username : '未登录');
      if (!data.logged_in) {
        setTimeout(() => { window.location.href = '/login'; }, 500);
      }
    } else {
      sessionText.textContent = '会话状态：获取失败';
    }
  } catch (err) {
    sessionText.textContent = '会话状态：请求失败';
  }
}

tabValidate.addEventListener('click', () => setActiveTab('validate'));
tabSubmit.addEventListener('click', () => setActiveTab('submit'));
ipTestButton.addEventListener('click', testIpConnectivity);
validateParseButton.addEventListener('click', parseValidationPayload);
validateButton.addEventListener('click', executeValidate);
validateModeDirect.addEventListener('change', () => setValidateMode('direct'));
validateModeStream.addEventListener('change', () => setValidateMode('stream'));
gotoFill.addEventListener('click', () => { window.location.href = '/fill'; });
logoutButton.addEventListener('click', () => { window.location.href = '/logout'; });

clearValidateFields();
loadSessionStatus();
