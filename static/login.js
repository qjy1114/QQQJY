var usernameInput = document.getElementById('username');
var passwordInput = document.getElementById('password');
var captchaInput = document.getElementById('captcha');
var loginButton = document.getElementById('loginButton');
var loginResult = document.getElementById('loginResult');
var captchaImage = document.getElementById('captchaImage');
var refreshCaptcha = document.getElementById('refreshCaptcha');

var isLoadingCaptcha = false;
var isLoggingIn = false;

function setResult(message, isError) {
  loginResult.textContent = message;
  loginResult.style.color = isError ? '#b91c1c' : '#0f172a';
}

function setLoading(btn, loading) {
  if (loading) {
    btn.disabled = true;
    btn.textContent = '加载中...';
  } else {
    btn.disabled = false;
  }
}

async function loadCaptcha() {
  if (isLoadingCaptcha) return;
  isLoadingCaptcha = true;
  captchaImage.style.opacity = '0.4';
  setLoading(refreshCaptcha, true);

  try {
    var resp = await fetch('/api/captcha');
    var data = await resp.json();
    if (!resp.ok) {
      setResult(data.error || '获取验证码失败', true);
      captchaImage.src = '';
      return;
    }
    captchaImage.src = data.src;
    captchaImage.style.opacity = '1';
    captchaInput.value = '';
    captchaInput.focus();
    setResult('请输入图形验证码。');
  } catch (err) {
    setResult('验证码请求失败：' + err.message, true);
    captchaImage.src = '';
  } finally {
    isLoadingCaptcha = false;
    setLoading(refreshCaptcha, false);
    refreshCaptcha.textContent = '刷新';
  }
}

async function doLogin() {
  if (isLoggingIn) return;

  var username = usernameInput.value.trim();
  var password = passwordInput.value.trim();
  var captcha = captchaInput.value.trim();

  if (!username || !password || !captcha) {
    setResult('请填写用户名、密码和验证码。', true);
    return;
  }

  isLoggingIn = true;
  loginButton.disabled = true;
  loginButton.textContent = '登录中...';
  setResult('正在登录，请稍候...');

  try {
    var resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password, captcha: captcha }),
    });
    var data = await resp.json();
    if (!resp.ok) {
      setResult(data.error || '登录失败', true);
      // Auto-refresh captcha on login failure
      if (data.needRefresh !== false) {
        loadCaptcha();
      }
      return;
    }
    setResult('登录成功，正在跳转...');
    setTimeout(function () {
      window.location.replace('/dashboard');
    }, 500);
  } catch (err) {
    setResult('登录请求失败：' + err.message, true);
  } finally {
    isLoggingIn = false;
    loginButton.disabled = false;
    loginButton.textContent = '登录平台';
  }
}

// ---- Event listeners ----

loginButton.addEventListener('click', doLogin);
refreshCaptcha.addEventListener('click', loadCaptcha);
captchaImage.addEventListener('click', loadCaptcha);

// Allow Enter key to submit
passwordInput.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});
captchaInput.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});

// Auto-load captcha on page load
window.addEventListener('load', function () {
  loadCaptcha();
  usernameInput.focus();
});
