const DEFAULT_SETTINGS = {
  apiBase: 'http://localhost:8000',
  accessToken: '',
  analysisMode: 'standard',
};

const apiBaseInput = document.getElementById('apiBase');
const accessTokenInput = document.getElementById('accessToken');
const analysisModeSelect = document.getElementById('analysisMode');
const saveBtn = document.getElementById('saveBtn');
const resetBtn = document.getElementById('resetBtn');
const statusEl = document.getElementById('status');

function normalizeApiBase(value) {
  const raw = (value || '').trim();
  if (!raw) {
    return DEFAULT_SETTINGS.apiBase;
  }
  if (/^https?:\/\//i.test(raw)) {
    return raw.replace(/\/+$/, '');
  }
  return `https://${raw}`.replace(/\/+$/, '');
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.className = isError ? 'error' : '';
}

async function loadSettings() {
  const settings = await chrome.storage.local.get(DEFAULT_SETTINGS);
  apiBaseInput.value = settings.apiBase || DEFAULT_SETTINGS.apiBase;
  accessTokenInput.value = settings.accessToken || '';
  analysisModeSelect.value = settings.analysisMode === 'experimental' ? 'experimental' : 'standard';
}

async function saveSettings() {
  try {
    const payload = {
      apiBase: normalizeApiBase(apiBaseInput.value),
      accessToken: (accessTokenInput.value || '').trim(),
      analysisMode: analysisModeSelect.value === 'experimental' ? 'experimental' : 'standard',
    };
    await chrome.storage.local.set(payload);
    setStatus('设置已保存。');
  } catch (err) {
    setStatus(`保存失败：${err.message || err}`, true);
  }
}

async function resetSettings() {
  try {
    await chrome.storage.local.set({ ...DEFAULT_SETTINGS });
    await loadSettings();
    setStatus('已恢复默认设置。');
  } catch (err) {
    setStatus(`重置失败：${err.message || err}`, true);
  }
}

saveBtn.addEventListener('click', saveSettings);
resetBtn.addEventListener('click', resetSettings);

loadSettings().catch((err) => {
  setStatus(`加载设置失败：${err.message || err}`, true);
});
