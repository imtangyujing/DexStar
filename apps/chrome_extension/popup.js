const DEFAULT_SETTINGS = {
  apiBase: 'http://localhost:8000',
  accessToken: '',
  analysisMode: 'standard',
};

const STATUS_TEXT = {
  queued: '排队中',
  downloading: '正在下载源文件',
  converting: '正在转换音频',
  analyzing: '正在分析音频',
  uploading: '正在上传文件',
  completed: '处理完成',
  failed: '处理失败',
  canceled: '已取消',
};

const STATUS_PROGRESS_FALLBACK = {
  queued: 5,
  downloading: 20,
  converting: 55,
  analyzing: 70,
  uploading: 85,
  completed: 100,
  failed: 0,
  canceled: 0,
};

const urlInput = document.getElementById('url');
const createBtn = document.getElementById('createBtn');
const downloadBtn = document.getElementById('downloadBtn');
const progressFill = document.getElementById('progressFill');
const statusEl = document.getElementById('status');
const metaEl = document.getElementById('meta');
const openOptionsEl = document.getElementById('openOptions');

let currentDownloadUrl = '';
let currentSettings = { ...DEFAULT_SETTINGS };

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setStatus(message, tone = 'normal') {
  statusEl.textContent = message;
  statusEl.className = 'status';
  if (tone === 'error') {
    statusEl.classList.add('error');
  }
  if (tone === 'ok') {
    statusEl.classList.add('ok');
  }
}

function setProgress(value) {
  const n = Math.max(0, Math.min(100, Number(value) || 0));
  progressFill.style.width = `${Math.round(n)}%`;
}

function resetDownloadState() {
  currentDownloadUrl = '';
  downloadBtn.className = 'download';
  downloadBtn.disabled = false;
  downloadBtn.textContent = '下载 MP3';
  metaEl.textContent = '';
}

function renderDownloadReady(job) {
  currentDownloadUrl = job.download_url || '';
  downloadBtn.className = 'download show';
  downloadBtn.disabled = !currentDownloadUrl;
  downloadBtn.textContent = '下载 MP3';

  const parts = [];
  if (job.final_filename) {
    parts.push(`文件名：${job.final_filename}`);
  }
  if (job.type_beat_name) {
    parts.push(`命名：${job.type_beat_name}`);
  }
  if (job.bpm) {
    parts.push(`BPM：${Math.round(job.bpm)}`);
  }
  metaEl.textContent = parts.join(' · ');
}

function renderDownloadError(message) {
  currentDownloadUrl = '';
  downloadBtn.className = 'download show error';
  downloadBtn.disabled = true;
  downloadBtn.textContent = message;
}

async function loadSettings() {
  const storage = await chrome.storage.local.get(DEFAULT_SETTINGS);
  currentSettings = {
    apiBase: normalizeApiBase(storage.apiBase),
    accessToken: (storage.accessToken || '').trim(),
    analysisMode: storage.analysisMode === 'experimental' ? 'experimental' : 'standard',
  };
}

async function apiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (currentSettings.accessToken) {
    headers.Authorization = `Bearer ${currentSettings.accessToken}`;
  }

  return fetch(`${currentSettings.apiBase}${path}`, {
    ...options,
    headers,
  });
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return {};
  }
}

function getErrorMessage(data, fallback) {
  if (!data) return fallback;
  if (typeof data.error_message === 'string' && data.error_message) return data.error_message;
  if (typeof data.detail === 'string' && data.detail) return data.detail;
  if (data.detail && typeof data.detail === 'object') {
    if (typeof data.detail.message === 'string' && data.detail.message) return data.detail.message;
    if (typeof data.detail.code === 'string' && data.detail.code) return `错误码：${data.detail.code}`;
  }
  return fallback;
}

async function createJobAndPoll() {
  const sourceUrl = (urlInput.value || '').trim();
  if (!sourceUrl) {
    setStatus('请先粘贴视频链接。', 'error');
    return;
  }

  createBtn.disabled = true;
  resetDownloadState();
  setProgress(3);
  setStatus('正在创建任务...');

  try {
    const response = await apiFetch('/api/v1/jobs', {
      method: 'POST',
      body: JSON.stringify({
        url: sourceUrl,
        analysis_mode: currentSettings.analysisMode,
      }),
    });
    const data = await safeJson(response);

    if (!response.ok) {
      throw new Error(getErrorMessage(data, '创建任务失败，请稍后重试。'));
    }
    if (!data.job_id) {
      throw new Error('创建任务失败，未返回 job_id。');
    }

    setStatus('任务已创建，开始轮询进度...');
    await pollJob(data.job_id);
  } catch (err) {
    setProgress(0);
    setStatus(`创建任务失败：${err.message || err}`, 'error');
    renderDownloadError('创建任务失败，请重试');
  } finally {
    createBtn.disabled = false;
  }
}

async function pollJob(jobId) {
  for (let i = 0; i < 120; i += 1) {
    const response = await apiFetch(`/api/v1/jobs/${jobId}`, { method: 'GET' });
    const data = await safeJson(response);

    if (!response.ok) {
      throw new Error(getErrorMessage(data, '轮询任务状态失败。'));
    }

    const status = data.status || 'queued';
    const progress = Number.isFinite(data.progress)
      ? data.progress
      : (STATUS_PROGRESS_FALLBACK[status] || 0);

    setProgress(progress);

    if (status === 'completed') {
      setProgress(100);
      setStatus('处理完成，可以下载。', 'ok');
      if (data.download_url) {
        renderDownloadReady(data);
      } else {
        renderDownloadError('下载链接生成失败');
      }
      return;
    }

    if (status === 'failed') {
      const message = getErrorMessage(data, '任务失败，请更换链接后重试。');
      setStatus(`任务失败：${message}`, 'error');
      renderDownloadError('任务失败');
      return;
    }

    if (status === 'canceled') {
      setStatus('任务已取消。', 'error');
      renderDownloadError('任务已取消');
      return;
    }

    setStatus(STATUS_TEXT[status] || '任务处理中...');
    await sleep(2000);
  }

  setStatus('任务超时，请稍后重试。', 'error');
  renderDownloadError('任务超时');
}

async function downloadCurrentFile() {
  if (!currentDownloadUrl) return;

  try {
    await chrome.downloads.download({
      url: currentDownloadUrl,
      saveAs: true,
      conflictAction: 'uniquify',
    });
  } catch (err) {
    window.open(currentDownloadUrl, '_blank', 'noopener,noreferrer');
  }
}

function bindEvents() {
  createBtn.addEventListener('click', createJobAndPoll);
  downloadBtn.addEventListener('click', downloadCurrentFile);
  openOptionsEl.addEventListener('click', (event) => {
    event.preventDefault();
    chrome.runtime.openOptionsPage();
  });
}

async function bootstrap() {
  bindEvents();
  await loadSettings();
  setStatus(`API：${currentSettings.apiBase}`);
}

bootstrap().catch((err) => {
  setStatus(`初始化失败：${err.message || err}`, 'error');
});
