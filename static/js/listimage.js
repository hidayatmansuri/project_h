/**
 * ListImage Frontend Controller
 * Handles drag-and-drop upload, status polling, preview overlays,
 * non-destructive editing (brush, wand, touch-up), and cleanup download flow.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const uploadCard = document.getElementById('liUploadCard');
  const fileInput = document.getElementById('liFileInput');
  const uploadForm = document.getElementById('liUploadForm');
  const progressCard = document.getElementById('liProgressCard');
  const queueBadge = document.getElementById('liQueueBadge');
  const progressText = document.getElementById('liProgressText');
  const cancelBtn = document.getElementById('liCancelBtn');
  const editorWorkspace = document.getElementById('liWorkspace');
  const previewImg = document.getElementById('liPreviewImg');
  const viewport = document.getElementById('liViewport');
  const guideOverlay = document.getElementById('liGuideOverlay');
  const edgeOverlay = document.getElementById('liEdgeOverlay');
  const whiteEdgeAlert = document.getElementById('liWhiteEdgeAlert');
  const objectsContainer = document.getElementById('liObjectsContainer');
  const drawingCanvas = document.getElementById('drawingCanvas');
  const errorAlert = document.getElementById('liErrorAlert');
  const errorMessage = document.getElementById('liErrorMessage');

  // Modals & Download
  const downloadModal = document.getElementById('liDownloadModal');
  const downloadBtn = document.getElementById('liDownloadBtn');
  const modalCloseBtn = document.getElementById('liModalCloseBtn');
  const confirmDownloadBtn = document.getElementById('liConfirmDownloadBtn');
  const formatCards = document.querySelectorAll('.li-format-card');

  // Mode Switcher Elements
  const modeSingleBtn = document.getElementById('liModeSingle');
  const modeBatchBtn = document.getElementById('liModeBatch');
  const uploadTitle = document.getElementById('liUploadTitle');
  const uploadDesc = document.getElementById('liUploadDesc');
  const uploadBtn = document.getElementById('liUploadBtn');
  const maxBatchSizeEl = document.getElementById('liMaxBatchSize');
  const maxBatchSize = maxBatchSizeEl ? parseInt(maxBatchSizeEl.value, 10) || 20 : 20;

  // Batch Workspace Elements
  const batchWorkspace = document.getElementById('liBatchWorkspace');
  const batchCounts = document.getElementById('liBatchCounts');
  const batchProgressStatusText = document.getElementById('liBatchProgressStatusText');
  const batchProgressPercent = document.getElementById('liBatchProgressPercent');
  const batchProgressBar = document.getElementById('liBatchProgressBar');
  const batchGrid = document.getElementById('liBatchGrid');
  const batchCancelBtn = document.getElementById('liBatchCancelBtn');
  const batchDiscardBtn = document.getElementById('liBatchDiscardBtn');
  const batchDownloadAllBtn = document.getElementById('liBatchDownloadAllBtn');
  const batchDownloadAllFooterBtn = document.getElementById('liBatchDownloadAllFooterBtn');
  const batchRestartBtn = document.getElementById('liBatchRestartBtn');
  const batchBgBtns = document.querySelectorAll('[data-batch-bg]');
  const batchReturnBar = document.getElementById('liBatchReturnBar');
  const batchCurrentFilename = document.getElementById('liBatchCurrentFilename');
  const backToBatchBtn = document.getElementById('liBackToBatchBtn');

  // Batch Download Modal Elements
  const batchDownloadModal = document.getElementById('liBatchDownloadModal');
  const batchModalCloseBtn = document.getElementById('liBatchModalCloseBtn');
  const confirmBatchDownloadBtn = document.getElementById('liConfirmBatchDownloadBtn');
  const batchFormatCards = document.querySelectorAll('.li-format-card[data-batch-format]');

  // State
  let isBatchMode = false;
  let currentBatchId = null;
  let batchPollInterval = null;
  let currentBatchBg = 'checker';
  let currentBatchFormat = 'PNG_WHITE';
  let activeBatchJobId = null;
  const batchItemsCache = new Map();

  let currentJobId = null;
  let pollInterval = null;
  let activeObjects = new Set();
  let allDetectedObjects = [];
  let currentFormat = 'PNG_WHITE';
  let currentBgMode = 'checker';
  let currentPreviewWhiteUrl = '';
  let currentPreviewTransUrl = '';
  let isDrawing = false;
  let currentTool = 'none'; // 'none', 'erase', 'restore', 'wand'
  let brushSize = 25;
  let wandTolerance = 30;
  let nudgeX = 0;
  let nudgeY = 0;
  let currentZoom = 1.0;
  let touchupApplied = false;

  // Initialize CSRF helper
  function getCsrfToken() {
    const cookie = document.cookie
      .split('; ')
      .find((row) => row.startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  function showError(msg) {
    if (errorAlert && errorMessage) {
      errorMessage.textContent = msg;
      errorAlert.style.display = 'flex';
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      alert(msg);
    }
  }

  function hideError() {
    if (errorAlert) {
      errorAlert.style.display = 'none';
    }
  }

  // Mode Switching
  if (modeSingleBtn && modeBatchBtn) {
    modeSingleBtn.addEventListener('click', () => {
      isBatchMode = false;
      modeSingleBtn.classList.add('active');
      modeBatchBtn.classList.remove('active');
      modeSingleBtn.setAttribute('aria-selected', 'true');
      modeBatchBtn.setAttribute('aria-selected', 'false');
      if (fileInput) fileInput.removeAttribute('multiple');
      if (uploadTitle) uploadTitle.textContent = 'Drop your image here or browse';
      if (uploadDesc) uploadDesc.textContent = 'Supports JPG, PNG, WEBP, and HEIC up to 25 MB (max 60 Megapixels). Automatically converts color space to sRGB and corrects rotation.';
      if (uploadBtn) uploadBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i> Select Image';
    });

    modeBatchBtn.addEventListener('click', () => {
      isBatchMode = true;
      modeBatchBtn.classList.add('active');
      modeSingleBtn.classList.remove('active');
      modeBatchBtn.setAttribute('aria-selected', 'true');
      modeSingleBtn.setAttribute('aria-selected', 'false');
      if (fileInput) fileInput.setAttribute('multiple', '');
      if (uploadTitle) uploadTitle.textContent = `Drop up to ${maxBatchSize} images here or browse`;
      if (uploadDesc) uploadDesc.textContent = `Batch mode: select or drop up to ${maxBatchSize} product images. Each image is processed with AI background removal and centered on an exact 2000×2000 pure white canvas.`;
      if (uploadBtn) uploadBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i> Select Images';
    });
  }

  // --- Upload & Drag-and-Drop ---
  if (uploadCard && fileInput) {
    ['dragenter', 'dragover'].forEach((eventName) => {
      uploadCard.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadCard.classList.add('drag-over');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      uploadCard.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadCard.classList.remove('drag-over');
      });
    });

    uploadCard.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length > 1 || isBatchMode) {
        handleBatchUpload(files);
      } else if (files.length === 1) {
        handleFileSelection(files[0]);
      }
    });

    uploadCard.addEventListener('click', (e) => {
      if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'INPUT') {
        fileInput.click();
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 1 || isBatchMode) {
        handleBatchUpload(e.target.files);
      } else if (e.target.files.length === 1) {
        handleFileSelection(e.target.files[0]);
      }
    });
  }

  function handleFileSelection(file) {
    hideError();
    // Pre-check size (25MB)
    if (file.size > 25 * 1024 * 1024) {
      showError(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximum allowed is 25 MB.`);
      return;
    }

    // Prepare FormData
    const formData = new FormData(uploadForm);
    formData.set('image', file);

    // Switch UI to Progress
    if (uploadCard) uploadCard.style.display = 'none';
    const optionsPanel = document.getElementById('liOptionsPanel');
    if (optionsPanel) optionsPanel.style.display = 'none';
    if (progressCard) progressCard.style.display = 'block';
    if (queueBadge) queueBadge.textContent = 'Uploading...';
    if (progressText) progressText.textContent = 'Sending file to server...';

    fetch('/listimage/upload/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken(),
      },
      body: formData,
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.success) {
          throw new Error(data.error || 'Upload failed.');
        }
        currentJobId = data.job_id;
        startPolling(currentJobId);
      })
      .catch((err) => {
        showError(err.message);
        if (progressCard) progressCard.style.display = 'none';
        if (uploadCard) uploadCard.style.display = 'block';
        if (optionsPanel) optionsPanel.style.display = 'block';
      });
  }

  // --- Status Polling ---
  function startPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(() => {
      fetch(`/listimage/status/${jobId}/`)
        .then((res) => {
          if (!res.ok) throw new Error('Failed to retrieve job status.');
          return res.json();
        })
        .then((data) => {
          if (data.status === 'queued') {
            if (queueBadge) queueBadge.textContent = data.queue_text || 'Queued';
            if (progressText) progressText.textContent = 'Waiting in queue...';
          } else if (data.status === 'processing') {
            if (queueBadge) queueBadge.textContent = 'Active';
            if (progressText) progressText.textContent = 'Removing background and centering on 2000x2000 pure white canvas...';
          } else if (data.status === 'done') {
            clearInterval(pollInterval);
            renderEditor(data);
          } else if (data.status === 'failed') {
            clearInterval(pollInterval);
            showError(data.error_message || 'Processing failed.');
            resetToUpload();
          }
        })
        .catch((err) => {
          clearInterval(pollInterval);
          showError(err.message);
          resetToUpload();
        });
    }, 1000);
  }

  function resetToUpload() {
    if (pollInterval) clearInterval(pollInterval);
    if (batchPollInterval) clearInterval(batchPollInterval);
    if (progressCard) progressCard.style.display = 'none';
    if (editorWorkspace) editorWorkspace.style.display = 'none';
    if (batchWorkspace) batchWorkspace.style.display = 'none';
    if (batchReturnBar) batchReturnBar.style.display = 'none';
    if (uploadCard) uploadCard.style.display = 'block';
    const optionsPanel = document.getElementById('liOptionsPanel');
    if (optionsPanel) optionsPanel.style.display = 'block';
    currentJobId = null;
    activeBatchJobId = null;
  }

  // --- Editor View Rendering ---
  function renderEditor(jobData) {
    if (progressCard) progressCard.style.display = 'none';
    if (uploadCard) uploadCard.style.display = 'none';
    const optionsPanel = document.getElementById('liOptionsPanel');
    if (optionsPanel) optionsPanel.style.display = 'none';
    if (editorWorkspace) editorWorkspace.style.display = 'flex';

    currentJobId = jobData.job_id;
    currentPreviewWhiteUrl = jobData.preview_url;
    currentPreviewTransUrl = jobData.preview_trans_url || (jobData.preview_url + (jobData.preview_url.includes('?') ? '&' : '?') + 'bg=transparent');
    updatePreview(currentBgMode === 'white' ? currentPreviewWhiteUrl : currentPreviewTransUrl);

    // White-on-white edge warning
    if (whiteEdgeAlert) {
      whiteEdgeAlert.style.display = jobData.warn_white_edges ? 'flex' : 'none';
    }

    // Objects list
    allDetectedObjects = jobData.detected_objects || [];
    renderObjectChips(allDetectedObjects);

    // Initialize drawing canvas
    setupDrawingCanvas();
  }

  function updatePreview(url) {
    if (previewImg) {
      previewImg.src = url;
    }
  }

  function renderObjectChips(objects) {
    if (!objectsContainer) return;
    objectsContainer.innerHTML = '';

    if (!objects || objects.length <= 1) {
      const parentRow = document.getElementById('liObjectsSection');
      if (parentRow) parentRow.style.display = 'none';
      return;
    }

    const parentRow = document.getElementById('liObjectsSection');
    if (parentRow) parentRow.style.display = 'block';

    allDetectedObjects = objects;
    activeObjects.clear();
    objects.forEach((obj) => {
      if (obj.active) activeObjects.add(obj.id);

      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `li-object-chip ${obj.active ? 'active' : ''}`;
      chip.innerHTML = `
        <i class="fa-solid ${obj.active ? 'fa-check' : 'fa-xmark'}"></i>
        <span>Object #${obj.id} (${(obj.area_ratio * 100).toFixed(0)}%)</span>
        ${obj.is_largest ? '<small style="opacity:0.8;">[Main]</small>' : ''}
      `;

      chip.addEventListener('click', () => {
        toggleObject(obj.id);
      });
      objectsContainer.appendChild(chip);
    });
  }

  const selectAllBtn = document.getElementById('liSelectAllObjectsBtn');
  if (selectAllBtn) {
    selectAllBtn.addEventListener('click', () => {
      if (allDetectedObjects && allDetectedObjects.length > 0) {
        activeObjects = new Set(allDetectedObjects.map((o) => o.id));
        allDetectedObjects.forEach((o) => (o.active = true));
        renderObjectChips(allDetectedObjects);
        sendEdits({ active_objects: Array.from(activeObjects) });
      }
    });
  }

  function toggleObject(objectId) {
    if (activeObjects.has(objectId)) {
      if (activeObjects.size <= 1) {
        showError('You must keep at least one object visible.');
        return;
      }
      activeObjects.delete(objectId);
    } else {
      activeObjects.add(objectId);
    }

    // Send edit update
    sendEdits({ active_objects: Array.from(activeObjects) });
  }

  // --- Background Switcher ---
  document.querySelectorAll('[data-bg]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-bg]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      const bg = btn.getAttribute('data-bg');
      currentBgMode = bg;
      viewport.classList.remove('bg-checker', 'bg-white', 'bg-dark');
      if (bg === 'checker') {
        viewport.classList.add('bg-checker');
        if (currentPreviewTransUrl) updatePreview(currentPreviewTransUrl);
      } else if (bg === 'white') {
        viewport.classList.add('bg-white');
        if (currentPreviewWhiteUrl) updatePreview(currentPreviewWhiteUrl);
      } else if (bg === 'dark') {
        viewport.classList.add('bg-dark');
        if (currentPreviewTransUrl) updatePreview(currentPreviewTransUrl);
      }
    });
  });

  // --- Overlay Toggles ---
  const toggleGuideBtn = document.getElementById('liToggleGuide');
  if (toggleGuideBtn && guideOverlay) {
    toggleGuideBtn.addEventListener('click', () => {
      const active = guideOverlay.classList.toggle('active');
      toggleGuideBtn.classList.toggle('active', active);
    });
  }

  const toggleEdgeBtn = document.getElementById('liToggleEdge');
  if (toggleEdgeBtn && edgeOverlay) {
    toggleEdgeBtn.addEventListener('click', () => {
      const active = edgeOverlay.classList.toggle('active');
      toggleEdgeBtn.classList.toggle('active', active);
    });
  }

  // --- Auto Touch-Up ---
  const touchupBtn = document.getElementById('liTouchupBtn');
  const touchupUndoBtn = document.getElementById('liTouchupUndoBtn');

  if (touchupBtn) {
    touchupBtn.addEventListener('click', () => {
      touchupBtn.disabled = true;
      touchupBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Touching up...';

      fetch(`/listimage/touchup/${currentJobId}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ enable: true }),
      })
        .then((r) => r.json())
        .then((res) => {
          touchupBtn.disabled = false;
          touchupBtn.innerHTML = '<i class="fa-solid fa-wand-magic"></i> Auto Touch-Up';
          if (res.success) {
            updatePreview(res.preview_url);
            touchupApplied = true;
            if (touchupUndoBtn) touchupUndoBtn.style.display = 'inline-flex';
          } else {
            showError(res.error || 'Touch-up failed.');
          }
        })
        .catch((e) => {
          touchupBtn.disabled = false;
          touchupBtn.innerHTML = '<i class="fa-solid fa-wand-magic"></i> Auto Touch-Up';
          showError(e.message);
        });
    });
  }

  if (touchupUndoBtn) {
    touchupUndoBtn.addEventListener('click', () => {
      fetch(`/listimage/touchup/${currentJobId}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ enable: false }),
      })
        .then((r) => r.json())
        .then((res) => {
          if (res.success) {
            updatePreview(res.preview_url);
            touchupApplied = false;
            touchupUndoBtn.style.display = 'none';
          }
        });
    });
  }

  // --- Brush & Drawing Setup ---
  function setupDrawingCanvas() {
    if (!drawingCanvas || !viewport) return;
    const rect = viewport.getBoundingClientRect();
    drawingCanvas.width = rect.width;
    drawingCanvas.height = rect.height;

    const ctx = drawingCanvas.getContext('2d');
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    function getPos(e) {
      const cRect = drawingCanvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return {
        x: clientX - cRect.left,
        y: clientY - cRect.top,
      };
    }

    drawingCanvas.addEventListener('pointerdown', (e) => {
      if (currentTool !== 'erase' && currentTool !== 'restore') return;
      isDrawing = true;
      const pos = getPos(e);
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      ctx.strokeStyle = currentTool === 'erase' ? 'rgba(255, 0, 0, 0.6)' : 'rgba(0, 255, 0, 0.6)';
      ctx.lineWidth = brushSize;
    });

    drawingCanvas.addEventListener('pointermove', (e) => {
      if (!isDrawing) return;
      const pos = getPos(e);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
    });

    const finishStroke = () => {
      if (!isDrawing) return;
      isDrawing = false;
      ctx.closePath();
      commitBrushStroke();
    };

    drawingCanvas.addEventListener('pointerup', finishStroke);
    drawingCanvas.addEventListener('pointerleave', finishStroke);
  }

  function commitBrushStroke() {
    if (!drawingCanvas || !currentJobId) return;
    const dataUrl = drawingCanvas.toDataURL('image/png');

    sendEdits({
      mask_delta_b64: dataUrl,
      brush_mode: currentTool,
    }).then(() => {
      // Clear overlay canvas
      const ctx = drawingCanvas.getContext('2d');
      ctx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);
    });
  }

  // Tool buttons
  const eraseToolBtn = document.getElementById('liEraseTool');
  const restoreToolBtn = document.getElementById('liRestoreTool');
  const brushSlider = document.getElementById('liBrushSize');

  if (eraseToolBtn) {
    eraseToolBtn.addEventListener('click', () => {
      if (currentTool === 'erase') {
        currentTool = 'none';
        eraseToolBtn.classList.remove('active');
      } else {
        currentTool = 'erase';
        eraseToolBtn.classList.add('active');
        if (restoreToolBtn) restoreToolBtn.classList.remove('active');
      }
    });
  }

  if (restoreToolBtn) {
    restoreToolBtn.addEventListener('click', () => {
      if (currentTool === 'restore') {
        currentTool = 'none';
        restoreToolBtn.classList.remove('active');
      } else {
        currentTool = 'restore';
        restoreToolBtn.classList.add('active');
        if (eraseToolBtn) eraseToolBtn.classList.remove('active');
      }
    });
  }

  if (brushSlider) {
    brushSlider.addEventListener('input', (e) => {
      brushSize = parseInt(e.target.value, 10);
    });
  }

  // --- Nudge & Zoom Controls ---
  const nudgeBtns = document.querySelectorAll('[data-nudge]');
  nudgeBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const dir = btn.getAttribute('data-nudge');
      const step = 5;
      if (dir === 'up') nudgeY -= step;
      if (dir === 'down') nudgeY += step;
      if (dir === 'left') nudgeX -= step;
      if (dir === 'right') nudgeX += step;
      sendEdits({ nudge_x: nudgeX, nudge_y: nudgeY });
    });
  });

  const zoomSlider = document.getElementById('liZoomSlider');
  if (zoomSlider) {
    zoomSlider.addEventListener('change', (e) => {
      currentZoom = parseFloat(e.target.value);
      sendEdits({ zoom: currentZoom });
    });
  }

  // --- Model Reprocessing ---
  const reprocessSelect = document.getElementById('liReprocessSelect');
  if (reprocessSelect) {
    reprocessSelect.addEventListener('change', (e) => {
      const newModel = e.target.value;
      if (confirm(`Re-run background removal with model "${newModel}"?`)) {
        sendEdits({
          model: newModel,
          reprocess_model: true,
        });
      }
    });
  }

  // --- API Edit Dispatcher ---
  function sendEdits(editsPayload) {
    if (!currentJobId) return Promise.reject(new Error('No active job'));

    return fetch(`/listimage/edit/${currentJobId}/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: JSON.stringify(editsPayload),
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.success) {
          showError(data.error || 'Failed to apply amendment.');
          return;
        }
        currentPreviewWhiteUrl = data.preview_url;
        currentPreviewTransUrl = data.preview_url + (data.preview_url.includes('?') ? '&' : '?') + 'bg=transparent';
        updatePreview(currentBgMode === 'white' ? currentPreviewWhiteUrl : currentPreviewTransUrl);
        if (data.warn_white_edges !== undefined && whiteEdgeAlert) {
          whiteEdgeAlert.style.display = data.warn_white_edges ? 'flex' : 'none';
        }
        if (data.detected_objects) {
          allDetectedObjects = data.detected_objects;
          renderObjectChips(data.detected_objects);
        }
      })
      .catch((err) => {
        showError(err.message);
      });
  }

  // --- Download & Automatic Cleanup Flow ---
  if (downloadBtn && downloadModal) {
    downloadBtn.addEventListener('click', () => {
      downloadModal.classList.add('active');
    });
  }

  if (modalCloseBtn && downloadModal) {
    modalCloseBtn.addEventListener('click', () => {
      downloadModal.classList.remove('active');
    });
  }

  formatCards.forEach((card) => {
    card.addEventListener('click', () => {
      formatCards.forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      currentFormat = card.getAttribute('data-format');
    });
  });

  if (confirmDownloadBtn) {
    confirmDownloadBtn.addEventListener('click', () => {
      if (!currentJobId) return;

      confirmDownloadBtn.disabled = true;
      confirmDownloadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Downloading...';

      const downloadUrl = `/listimage/download/${currentJobId}/?format=${currentFormat}`;

      // 1. Fetch file blob to trigger browser download
      fetch(downloadUrl)
        .then((response) => {
          if (!response.ok) throw new Error('Download failed on server.');
          return response.blob();
        })
        .then((blob) => {
          // Trigger browser file download
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          let filename = `listimage_2000x2000_white_${currentJobId.substring(0, 8)}.png`;
          if (currentFormat === 'PNG_TRANSPARENT') {
            filename = `listimage_transparent_${currentJobId.substring(0, 8)}.png`;
          } else if (currentFormat === 'JPEG') {
            filename = `listimage_2000x2000_${currentJobId.substring(0, 8)}.jpg`;
          }
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          a.remove();

          // 2. Perform post-download cleanup: delete files and DB record, redirect to index
          if (activeBatchJobId) {
            closeDownloadModal();
            returnToBatchGallery();
            return;
          }

          return fetch(`/listimage/cleanup/${currentJobId}/`, {
            method: 'POST',
            headers: {
              'X-CSRFToken': getCsrfToken(),
              'X-Requested-With': 'XMLHttpRequest',
            },
          }).then(() => {
            // 3. Return to listimage main page
            window.location.href = '/listimage/';
          });
        })
        .catch((err) => {
          confirmDownloadBtn.disabled = false;
          confirmDownloadBtn.innerHTML = '<i class="fa-solid fa-download"></i> Save & Cleanup';
          showError(`Download error: ${err.message}`);
        });
    });
  }

  // --- Cancel / Start Over ---
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      if (currentJobId && confirm('Cancel this processing job and start over?')) {
        fetch(`/listimage/cancel/${currentJobId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        }).then(() => {
          window.location.href = '/listimage/';
        });
      } else {
        window.location.href = '/listimage/';
      }
    });
  }

  const restartBtn = document.getElementById('liRestartBtn');
  if (restartBtn) {
    restartBtn.addEventListener('click', () => {
      if (activeBatchJobId) {
        if (confirm('Return to batch gallery? Unsaved edits on this image will be discarded.')) {
          returnToBatchGallery();
        }
        return;
      }
      if (confirm('Discard edits and return to upload? This will clean up the current session files.')) {
        if (currentJobId) {
          fetch(`/listimage/cleanup/${currentJobId}/`, {
            method: 'POST',
            headers: {
              'X-CSRFToken': getCsrfToken(),
              'X-Requested-With': 'XMLHttpRequest',
            },
          }).then(() => {
            window.location.href = '/listimage/';
          });
        } else {
          window.location.href = '/listimage/';
        }
      }
    });
  }

  // ==========================================================================
  // Batch Mode Operations (Photoroom-Style Batch Processing)
  // ==========================================================================

  function handleBatchUpload(files) {
    hideError();
    if (!files || files.length === 0) return;

    if (files.length > maxBatchSize) {
      showError(`Too many files selected (${files.length}). Maximum allowed per batch is ${maxBatchSize}.`);
      return;
    }

    for (let i = 0; i < files.length; i++) {
      if (files[i].size > 25 * 1024 * 1024) {
        showError(`File "${files[i].name}" is too large (${(files[i].size / (1024 * 1024)).toFixed(1)} MB). Maximum allowed is 25 MB.`);
        return;
      }
    }

    const formData = new FormData(uploadForm);
    formData.delete('image');
    formData.delete('images');
    for (let i = 0; i < files.length; i++) {
      formData.append('images', files[i]);
    }

    // Switch UI to Batch Workspace
    if (uploadCard) uploadCard.style.display = 'none';
    const optionsPanel = document.getElementById('liOptionsPanel');
    if (optionsPanel) optionsPanel.style.display = 'none';
    if (editorWorkspace) editorWorkspace.style.display = 'none';
    if (progressCard) progressCard.style.display = 'none';
    if (batchWorkspace) batchWorkspace.style.display = 'flex';

    if (batchCounts) batchCounts.textContent = `Uploading ${files.length} images to server...`;
    if (batchProgressStatusText) batchProgressStatusText.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Uploading images...';
    if (batchProgressPercent) batchProgressPercent.textContent = '0%';
    if (batchProgressBar) batchProgressBar.style.width = '0%';
    if (batchGrid) batchGrid.innerHTML = '';
    if (batchDownloadAllBtn) batchDownloadAllBtn.disabled = true;
    if (batchDownloadAllFooterBtn) batchDownloadAllFooterBtn.disabled = true;
    if (batchCancelBtn) batchCancelBtn.style.display = 'inline-flex';
    if (batchDiscardBtn) batchDiscardBtn.style.display = 'none';

    fetch('/listimage/batch/upload/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken(),
      },
      body: formData,
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.success) {
          throw new Error(data.error || 'Batch upload failed.');
        }
        currentBatchId = data.batch_id;
        startBatchPolling(currentBatchId);
      })
      .catch((err) => {
        showError(err.message);
        resetToUpload();
      });
  }

  function startBatchPolling(batchId) {
    if (batchPollInterval) clearInterval(batchPollInterval);

    const poll = () => {
      fetch(`/listimage/batch/status/${batchId}/`)
        .then((res) => {
          if (!res.ok) throw new Error('Failed to retrieve batch status.');
          return res.json();
        })
        .then((data) => {
          updateBatchDashboard(data);
          if (data.is_complete) {
            clearInterval(batchPollInterval);
            batchPollInterval = null;
          }
        })
        .catch((err) => {
          clearInterval(batchPollInterval);
          batchPollInterval = null;
          showError(err.message);
        });
    };

    poll();
    batchPollInterval = setInterval(poll, 1200);
  }

  function updateBatchDashboard(data) {
    if (batchProgressPercent) batchProgressPercent.textContent = `${data.percent}%`;
    if (batchProgressBar) batchProgressBar.style.width = `${data.percent}%`;

    const summaryText = `${data.completed_count} of ${data.total_count} complete` +
      (data.processing_count > 0 ? ` &bull; ${data.processing_count} processing` : '') +
      (data.queued_count > 0 ? ` &bull; ${data.queued_count} queued` : '') +
      (data.failed_count > 0 ? ` &bull; <span style="color: var(--li-danger);">${data.failed_count} failed</span>` : '');
    if (batchCounts) batchCounts.innerHTML = summaryText;

    if (data.is_complete) {
      if (batchProgressStatusText) {
        batchProgressStatusText.innerHTML = '<i class="fa-solid fa-circle-check" style="color: var(--li-success);"></i> All images processed!';
      }
      if (batchCancelBtn) batchCancelBtn.style.display = 'none';
      if (batchDiscardBtn) batchDiscardBtn.style.display = 'inline-flex';
    } else {
      if (batchProgressStatusText) {
        batchProgressStatusText.innerHTML = '<i class="fa-solid fa-gear fa-spin"></i> Processing images in background...';
      }
      if (batchCancelBtn) batchCancelBtn.style.display = 'inline-flex';
      if (batchDiscardBtn) batchDiscardBtn.style.display = 'none';
    }

    const canDownload = data.completed_count > 0;
    if (batchDownloadAllBtn) batchDownloadAllBtn.disabled = !canDownload;
    if (batchDownloadAllFooterBtn) batchDownloadAllFooterBtn.disabled = !canDownload;

    renderBatchCards(data.items);
  }

  function renderBatchCards(items) {
    if (!batchGrid || !items) return;

    items.forEach((item) => {
      batchItemsCache.set(item.job_id, item);
      let card = document.getElementById(`liBatchCard-${item.job_id}`);

      if (!card) {
        card = document.createElement('div');
        card.id = `liBatchCard-${item.job_id}`;
        card.className = 'li-batch-card';
        batchGrid.appendChild(card);
      }

      const prevStatus = card.dataset.status;
      if (prevStatus === item.status && item.status !== 'processing') {
        return;
      }
      card.dataset.status = item.status;

      let statusBadge = '';
      if (item.status === 'queued') {
        statusBadge = '<span class="li-status-badge status-queued"><i class="fa-regular fa-clock"></i> Queued</span>';
      } else if (item.status === 'processing') {
        statusBadge = '<span class="li-status-badge status-processing"><i class="fa-solid fa-gear fa-spin"></i> Processing</span>';
      } else if (item.status === 'done') {
        statusBadge = '<span class="li-status-badge status-done"><i class="fa-solid fa-check"></i> Ready</span>';
      } else if (item.status === 'failed') {
        statusBadge = '<span class="li-status-badge status-failed"><i class="fa-solid fa-triangle-exclamation"></i> Failed</span>';
      }

      let viewportContent = '';
      if (item.status === 'queued' || item.status === 'processing') {
        viewportContent = `
          <div class="li-batch-card-placeholder">
            <i class="fa-solid fa-gear fa-spin li-spinner"></i>
            <span>${item.status === 'queued' ? 'Waiting in queue...' : 'Removing background & centering...'}</span>
          </div>
        `;
      } else if (item.status === 'failed') {
        viewportContent = `
          <div class="li-batch-card-placeholder" style="color: var(--li-danger);">
            <i class="fa-solid fa-circle-xmark" style="font-size: 2rem;"></i>
            <span style="font-size: 0.78rem;">${item.error_message || 'Processing error'}</span>
          </div>
        `;
      } else if (item.status === 'done') {
        const imgSrc = currentBatchBg === 'white' ? item.preview_url : (item.preview_trans_url || item.preview_url);
        viewportContent = `
          <img class="li-batch-card-img" src="${imgSrc}" alt="${item.filename}">
          <div class="li-batch-card-overlay">
            <button type="button" class="li-batch-overlay-btn" data-edit-job="${item.job_id}">
              <i class="fa-solid fa-wand-magic-sparkles"></i> Edit in Canvas
            </button>
            <a class="li-batch-overlay-btn" href="${item.download_url}?format=PNG_WHITE" download>
              <i class="fa-solid fa-download"></i> White PNG
            </a>
          </div>
        `;
      }

      let footerContent = '';
      if (item.status === 'done') {
        footerContent = `
          <span><i class="fa-solid fa-layer-group"></i> ${item.detected_objects_count || 1} obj &bull; 2000&times;2000</span>
          <div class="li-batch-card-actions">
            <button type="button" class="li-batch-action-btn" data-edit-job="${item.job_id}" title="Edit in canvas">
              <i class="fa-solid fa-pen-to-square"></i> Edit
            </button>
            <a class="li-batch-action-btn" href="${item.download_url}?format=PNG_WHITE" download title="Download White PNG">
              <i class="fa-solid fa-download"></i>
            </a>
          </div>
        `;
      } else if (item.status === 'failed') {
        footerContent = `<span style="color: var(--li-danger);">Failed</span>`;
      } else {
        footerContent = `<span>Exact 2000&times;2000 px canvas</span>`;
      }

      card.innerHTML = `
        <div class="li-batch-card-header">
          <span class="li-batch-card-filename" title="${item.filename}">${item.filename}</span>
          ${statusBadge}
        </div>
        <div class="li-batch-card-viewport bg-${currentBatchBg}">
          ${viewportContent}
        </div>
        <div class="li-batch-card-footer">
          ${footerContent}
        </div>
      `;
    });
  }

  // Open a Batch Item in the Canvas Editor
  if (batchGrid) {
    batchGrid.addEventListener('click', (e) => {
      const editBtn = e.target.closest('[data-edit-job]');
      if (editBtn) {
        const jobId = editBtn.dataset.editJob;
        openBatchJobInEditor(jobId);
      }
    });
  }

  function openBatchJobInEditor(jobId) {
    const item = batchItemsCache.get(jobId);
    activeBatchJobId = jobId;

    if (batchWorkspace) batchWorkspace.style.display = 'none';
    if (editorWorkspace) editorWorkspace.style.display = 'flex';
    if (batchReturnBar) {
      batchReturnBar.style.display = 'flex';
      if (batchCurrentFilename && item) {
        batchCurrentFilename.textContent = item.filename;
      }
    }

    fetch(`/listimage/status/${jobId}/`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load item status.');
        return res.json();
      })
      .then((jobData) => {
        renderEditor(jobData);
      })
      .catch((err) => {
        showError(err.message);
        returnToBatchGallery();
      });
  }

  function returnToBatchGallery() {
    if (editorWorkspace) editorWorkspace.style.display = 'none';
    if (batchReturnBar) batchReturnBar.style.display = 'none';
    if (batchWorkspace) batchWorkspace.style.display = 'flex';

    if (activeBatchJobId && currentBatchId) {
      fetch(`/listimage/status/${activeBatchJobId}/`)
        .then((r) => r.json())
        .then((updatedItem) => {
          if (updatedItem.status === 'done') {
            const card = document.getElementById(`liBatchCard-${activeBatchJobId}`);
            if (card) {
              const img = card.querySelector('.li-batch-card-img');
              if (img) {
                const url = currentBatchBg === 'white' ? updatedItem.preview_url : updatedItem.preview_trans_url;
                img.src = url + (url.includes('?') ? '&' : '?') + `t=${Date.now()}`;
              }
            }
          }
        });
    }
    activeBatchJobId = null;
  }

  if (backToBatchBtn) {
    backToBatchBtn.addEventListener('click', () => {
      returnToBatchGallery();
    });
  }

  // Batch Background Mode Switcher
  batchBgBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      batchBgBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      currentBatchBg = btn.dataset.batchBg;

      document.querySelectorAll('.li-batch-card-viewport').forEach((vp) => {
        vp.classList.remove('bg-checker', 'bg-white', 'bg-dark');
        vp.classList.add(`bg-${currentBatchBg}`);
      });

      batchItemsCache.forEach((item) => {
        if (item.status === 'done') {
          const card = document.getElementById(`liBatchCard-${item.job_id}`);
          if (card) {
            const img = card.querySelector('.li-batch-card-img');
            if (img) {
              img.src = currentBatchBg === 'white' ? item.preview_url : (item.preview_trans_url || item.preview_url);
            }
          }
        }
      });
    });
  });

  // Batch Download Modal
  function openBatchDownloadModal() {
    if (batchDownloadModal) {
      batchDownloadModal.classList.add('active');
    }
  }

  function closeBatchDownloadModal() {
    if (batchDownloadModal) {
      batchDownloadModal.classList.remove('active');
    }
  }

  if (batchDownloadAllBtn) batchDownloadAllBtn.addEventListener('click', openBatchDownloadModal);
  if (batchDownloadAllFooterBtn) batchDownloadAllFooterBtn.addEventListener('click', openBatchDownloadModal);
  if (batchModalCloseBtn) batchModalCloseBtn.addEventListener('click', closeBatchDownloadModal);

  batchFormatCards.forEach((card) => {
    card.addEventListener('click', () => {
      batchFormatCards.forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      currentBatchFormat = card.dataset.batchFormat;
    });
  });

  if (confirmBatchDownloadBtn) {
    confirmBatchDownloadBtn.addEventListener('click', () => {
      if (!currentBatchId) return;
      closeBatchDownloadModal();
      window.location.href = `/listimage/batch/download/${currentBatchId}/?format=${currentBatchFormat}`;
    });
  }

  // Batch Cancel & Cleanup
  if (batchCancelBtn) {
    batchCancelBtn.addEventListener('click', () => {
      if (!currentBatchId) return;
      if (confirm('Cancel this batch and discard progress?')) {
        if (batchPollInterval) clearInterval(batchPollInterval);
        fetch(`/listimage/batch/cancel/${currentBatchId}/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        }).then(() => {
          window.location.href = '/listimage/';
        });
      }
    });
  }

  const handleBatchCleanup = () => {
    if (!currentBatchId) return;
    if (confirm('Start a new batch? This will clean up the current batch session files.')) {
      if (batchPollInterval) clearInterval(batchPollInterval);
      fetch(`/listimage/batch/cleanup/${currentBatchId}/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
      }).then(() => {
        window.location.href = '/listimage/';
      });
    }
  };

  if (batchDiscardBtn) batchDiscardBtn.addEventListener('click', handleBatchCleanup);
  if (batchRestartBtn) batchRestartBtn.addEventListener('click', handleBatchCleanup);

  // Resume Existing Session on Page Load (Single Job or Batch)
  const activeBatchEl = document.getElementById('liActiveBatchId');
  const activeJobEl = document.getElementById('liActiveJobId');

  if (activeBatchEl && activeBatchEl.value) {
    const existingBatchId = activeBatchEl.value;
    const existingBatchStatus = document.getElementById('liActiveBatchStatus')?.value;
    if (existingBatchStatus === 'queued' || existingBatchStatus === 'processing') {
      if (uploadCard) uploadCard.style.display = 'none';
      const optionsPanel = document.getElementById('liOptionsPanel');
      if (optionsPanel) optionsPanel.style.display = 'none';
      if (batchWorkspace) batchWorkspace.style.display = 'flex';
      currentBatchId = existingBatchId;
      startBatchPolling(existingBatchId);
    } else if (existingBatchStatus === 'done') {
      if (uploadCard) uploadCard.style.display = 'none';
      const optionsPanel = document.getElementById('liOptionsPanel');
      if (optionsPanel) optionsPanel.style.display = 'none';
      if (batchWorkspace) batchWorkspace.style.display = 'flex';
      currentBatchId = existingBatchId;
      fetch(`/listimage/batch/status/${existingBatchId}/`)
        .then((r) => r.json())
        .then((data) => {
          updateBatchDashboard(data);
        });
    }
  } else if (activeJobEl && activeJobEl.value) {
    const existingId = activeJobEl.value;
    const existingStatus = document.getElementById('liActiveJobStatus')?.value;
    if (existingStatus === 'queued' || existingStatus === 'processing') {
      if (uploadCard) uploadCard.style.display = 'none';
      const optionsPanel = document.getElementById('liOptionsPanel');
      if (optionsPanel) optionsPanel.style.display = 'none';
      if (progressCard) progressCard.style.display = 'block';
      currentJobId = existingId;
      startPolling(existingId);
    } else if (existingStatus === 'done') {
      fetch(`/listimage/status/${existingId}/`)
        .then((r) => r.json())
        .then((data) => {
          if (data.status === 'done') {
            renderEditor(data);
          }
        });
    }
  }
});
