/**
 * Question Extractor — Frontend Controller
 * Controls continuous question pulling from LeetCode & HackerRank into questions.json.
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const viewJsonBtn = document.getElementById('viewJsonBtn');
  const clearBtn = document.getElementById('clearBtn');
  const downloadBtn = document.getElementById('downloadBtn');

  const statusBadge = document.getElementById('statusBadge');
  const statusText = document.getElementById('statusText');
  const currentActionText = document.getElementById('currentActionText');

  const statTotal = document.getElementById('statTotal');
  const statLeetcode = document.getElementById('statLeetcode');
  const statHackerrank = document.getElementById('statHackerrank');
  const statSkipped = document.getElementById('statSkipped');

  const streamContainer = document.getElementById('streamContainer');
  const streamEmpty = document.getElementById('streamEmpty');
  const streamList = document.getElementById('streamList');

  const jsonModal = document.getElementById('jsonModal');
  const jsonContent = document.getElementById('jsonContent');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const copyJsonBtn = document.getElementById('copyJsonBtn');
  const toast = document.getElementById('toast');

  let pollInterval = null;
  let isRunning = false;
  const displayedQuestionIds = new Set();

  // Toast Helper
  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 2800);
  }

  // Update Status UI
  function updateStatusUI(running, actionText, statusMsg) {
    isRunning = running;
    startBtn.disabled = running;
    stopBtn.disabled = !running;

    if (running) {
      statusBadge.className = 'live-status-badge running';
      statusText.textContent = 'EXTRACTING...';
      currentActionText.textContent = actionText || 'Pulling questions from LeetCode & HackerRank...';
    } else {
      if (statusMsg === 'Stopped') {
        statusBadge.className = 'live-status-badge stopped';
        statusText.textContent = 'STOPPED';
        currentActionText.textContent = 'Extraction stopped. Click "Start Extraction" to resume.';
      } else {
        statusBadge.className = 'live-status-badge';
        statusText.textContent = 'READY';
        currentActionText.textContent = actionText || 'Ready. Click "Start Extraction" to begin.';
      }
    }
  }

  // Render a question stream card
  function renderQuestionCard(item, prepend = true) {
    const uniqueKey = `${item.platform}:${item.slug}`;
    if (displayedQuestionIds.has(uniqueKey)) {
      return;
    }
    displayedQuestionIds.add(uniqueKey);

    // Hide empty state, show list
    if (streamEmpty) streamEmpty.style.display = 'none';
    if (streamList) streamList.style.display = 'flex';

    const card = document.createElement('div');
    card.className = 'stream-card';
    card.id = `card-${item.platform}-${item.slug}`;

    const platClass = item.platform.toLowerCase();
    const diff = (item.difficulty || 'Unknown').toLowerCase();
    const diffClass = ['easy', 'medium', 'hard'].includes(diff) ? diff : 'unknown';

    const tagsHtml = (item.tags || []).slice(0, 3).map(t => `<span class="tag-pill">${t}</span>`).join('');

    card.innerHTML = `
      <div class="stream-card-left">
        <span class="platform-badge ${platClass}">${item.platform}</span>
        <div class="problem-info">
          <div class="problem-title-row">
            <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="problem-title-link">
              ${item.id ? item.id + '. ' : ''}${item.title}
            </a>
            <span class="diff-badge ${diffClass}">${item.difficulty || 'Unknown'}</span>
          </div>
          <div class="problem-meta-row">
            <span>Slug: <code>${item.slug}</code></span>
            ${tagsHtml ? `<div class="problem-tags-list">${tagsHtml}</div>` : ''}
          </div>
        </div>
      </div>
      <div class="stream-card-right">
        <span class="saved-pill">✓ Saved to JSON</span>
      </div>
    `;

    if (prepend && streamList.firstChild) {
      streamList.insertBefore(card, streamList.firstChild);
    } else {
      streamList.appendChild(card);
    }
  }

  // Fetch status from server
  async function fetchStatus() {
    try {
      const res = await fetch('/api/extractor/status');
      if (!res.ok) return;
      const data = await res.json();

      // Update counters
      if (data.stats) {
        statTotal.textContent = data.stats.total_questions || 0;
        statLeetcode.textContent = data.stats.leetcode_count || 0;
        statHackerrank.textContent = data.stats.hackerrank_count || 0;
        statSkipped.textContent = data.stats.duplicates_skipped || 0;
      }

      // Update Running status
      updateStatusUI(data.is_running, data.current_action, data.status);

      // Render recent extracted items
      if (data.recent_extracted && Array.isArray(data.recent_extracted)) {
        // Render in chronological order
        const reversed = [...data.recent_extracted].reverse();
        reversed.forEach(item => renderQuestionCard(item, true));
      }
    } catch (err) {
      console.warn('Status poll error:', err);
    }
  }

  // Load existing questions initially from database
  async function loadInitialQuestions() {
    try {
      const res = await fetch('/api/questions?limit=25');
      if (!res.ok) return;
      const data = await res.json();

      if (data.stats) {
        statTotal.textContent = data.stats.total_questions || 0;
        statLeetcode.textContent = data.stats.leetcode_count || 0;
        statHackerrank.textContent = data.stats.hackerrank_count || 0;
        statSkipped.textContent = data.stats.duplicates_skipped || 0;
      }

      if (data.questions && data.questions.length > 0) {
        data.questions.forEach(item => renderQuestionCard(item, false));
      }
    } catch (err) {
      console.warn('Could not load initial questions:', err);
    }
  }

  // Start polling
  function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(fetchStatus, 900);
  }

  // Controls: Start Extraction
  startBtn.addEventListener('click', async () => {
    try {
      startBtn.disabled = true;
      const res = await fetch('/api/extractor/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delay: 0.8 }),
      });
      const data = await res.json();
      if (data.success) {
        updateStatusUI(true, 'Extraction started...', 'Running');
        showToast('⚡ Continuous extraction started! Pulling into questions.json...');
      }
    } catch (err) {
      showToast('Error starting extractor: ' + err.message);
      startBtn.disabled = false;
    }
  });

  // Controls: Stop Extraction
  stopBtn.addEventListener('click', async () => {
    try {
      stopBtn.disabled = true;
      const res = await fetch('/api/extractor/stop', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        updateStatusUI(false, 'Extraction stopped by user.', 'Stopped');
        showToast('⏹ Extractor stopped. All questions safely saved.');
      }
    } catch (err) {
      showToast('Error stopping extractor: ' + err.message);
      stopBtn.disabled = false;
    }
  });

  // Controls: Download single questions.json file
  if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
      showToast('📥 Downloading questions.json (single dataset file)...');
      try {
        await fetch('/api/questions/save', { method: 'POST' });
      } catch (err) {
        console.warn('Sync questions.json error:', err);
      }
    });
  }

  // Controls: View JSON Preview
  viewJsonBtn.addEventListener('click', async () => {
    try {
      jsonModal.classList.add('active');
      jsonContent.textContent = 'Loading questions.json...';

      const res = await fetch('/api/questions?limit=10');
      const data = await res.json();
      const formatted = JSON.stringify(data.questions, null, 2);
      jsonContent.textContent = formatted || '[]';
    } catch (err) {
      jsonContent.textContent = 'Failed to load JSON preview: ' + err.message;
    }
  });

  // Modal Close
  closeModalBtn.addEventListener('click', () => {
    jsonModal.classList.remove('active');
  });

  jsonModal.addEventListener('click', (e) => {
    if (e.target === jsonModal) {
      jsonModal.classList.remove('active');
    }
  });

  // Copy JSON Button
  copyJsonBtn.addEventListener('click', () => {
    if (navigator.clipboard && jsonContent.textContent) {
      navigator.clipboard.writeText(jsonContent.textContent)
        .then(() => showToast('Copied JSON preview to clipboard!'))
        .catch(() => showToast('Could not copy to clipboard'));
    }
  });

  // Controls: Reset / Clear dataset
  clearBtn.addEventListener('click', async () => {
    const confirmClear = confirm('Are you sure you want to reset questions.json to 0 questions?');
    if (!confirmClear) return;

    try {
      const res = await fetch('/api/questions', { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        displayedQuestionIds.clear();
        if (streamList) streamList.innerHTML = '';
        if (streamEmpty) streamEmpty.style.display = 'flex';
        statTotal.textContent = '0';
        statLeetcode.textContent = '0';
        statHackerrank.textContent = '0';
        statSkipped.textContent = '0';
        showToast('questions.json has been reset.');
      }
    } catch (err) {
      showToast('Error resetting dataset: ' + err.message);
    }
  });

  // Initialization
  loadInitialQuestions();
  fetchStatus();
  startPolling();
});
