/**
 * ListImage SVG Vectorization Wizard Client Script.
 * Stage 5: Interactive client-side swatch recolouring, click-to-pick region,
 * undo stack, reset to original, near-white removal, and blob download.
 */

document.addEventListener('DOMContentLoaded', () => {
    // CSRF helper
    function getCsrfToken() {
        const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input) return input.value;
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    // Helper: is near-white (all RGB >= 245)
    function isNearWhite(hex) {
        if (!hex || typeof hex !== 'string') return false;
        let h = hex.trim().replace('#', '');
        if (h.length === 3) h = h.split('').map(c => c + c).join('');
        if (h.length !== 6) return false;
        const r = parseInt(h.substring(0, 2), 16);
        const g = parseInt(h.substring(2, 4), 16);
        const b = parseInt(h.substring(4, 6), 16);
        return r >= 245 && g >= 245 && b >= 245;
    }

    // =========================================================================
    // 1. UPLOAD STEP
    // =========================================================================
    const uploadForm = document.getElementById('liSvgUploadForm');
    const fileInput = document.getElementById('liSvgFileInput');
    const preModeBtns = document.querySelectorAll('[data-premode]');
    const preColorModeInput = document.getElementById('liPreColorMode');

    if (uploadForm && fileInput) {
        function handleFileSelection() {
            if (fileInput.files && fileInput.files.length > 0) {
                const uploadCard = document.getElementById('liSvgUploadCard');
                if (uploadCard) {
                    uploadCard.innerHTML = `
                        <i class="fa-solid fa-spinner fa-spin li-upload-icon"></i>
                        <h2 class="li-upload-title">Uploading image...</h2>
                        <p class="li-upload-desc">Please wait while your image is prepared for vector tracing.</p>
                    `;
                }
                uploadForm.submit();
            }
        }

        fileInput.addEventListener('change', handleFileSelection);

        preModeBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                preModeBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (preColorModeInput) {
                    preColorModeInput.value = btn.dataset.premode;
                }
            });
        });

        const uploadCard = document.getElementById('liSvgUploadCard');
        if (uploadCard) {
            ['dragenter', 'dragover'].forEach(eventName => {
                uploadCard.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    uploadCard.style.borderColor = 'var(--li-accent, #6366f1)';
                    uploadCard.style.background = 'rgba(99, 102, 241, 0.05)';
                });
            });

            ['dragleave', 'drop'].forEach(eventName => {
                uploadCard.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    uploadCard.style.borderColor = '';
                    uploadCard.style.background = '';
                });
            });

            uploadCard.addEventListener('drop', (e) => {
                if (e.dataTransfer && e.dataTransfer.files.length > 0) {
                    fileInput.files = e.dataTransfer.files;
                    handleFileSelection();
                }
            });
        }
    }

    // =========================================================================
    // 2. OPTIONS & PREVIEW WIZARD
    // =========================================================================
    const jobIdEl = document.getElementById('liJobId');
    if (!jobIdEl) return;

    const jobId = jobIdEl.value;
    const statusUrl = document.getElementById('liStatusUrl').value;
    const renderUrl = document.getElementById('liRenderUrl').value;
    const previewUrl = document.getElementById('liPreviewUrl').value;
    const downloadUrl = document.getElementById('liDownloadUrl').value;
    const cancelUrl = document.getElementById('liCancelUrl').value;
    const cleanupUrl = document.getElementById('liCleanupUrl') ? document.getElementById('liCleanupUrl').value : cancelUrl;
    const recolorUrl = document.getElementById('liRecolorUrl') ? document.getElementById('liRecolorUrl').value : '';

    const processingBanner = document.getElementById('liSvgProcessingBanner');
    const statusHeading = document.getElementById('liSvgStatusHeading');
    const errorAlert = document.getElementById('liSvgErrorAlert');
    const errorMessage = document.getElementById('liSvgErrorMessage');
    const svgObject = document.getElementById('liSvgObject');
    const svgViewport = document.getElementById('liSvgViewport');

    // Stats elements
    const statPaths = document.getElementById('liStatPaths');
    const statColors = document.getElementById('liStatColors');
    const statSize = document.getElementById('liStatSize');
    const sizeWarnAlert = document.getElementById('liSizeWarnAlert');

    // Controls
    const modeBtns = document.querySelectorAll('#liSvgModeSelector button');
    const colorModeInput = document.getElementById('liColorModeInput');
    const monoControls = document.getElementById('liMonochromeControls');
    const colorControls = document.getElementById('liColorControls');
    const hybridMonoGroup = document.getElementById('liHybridMonoColorGroup');

    const monoColorInput = document.getElementById('liMonoColor');
    const monoColorVal = document.getElementById('liMonoColorVal');
    const hybridMonoColorInput = document.getElementById('liHybridMonoColor');
    const hybridMonoColorVal = document.getElementById('liHybridMonoColorVal');

    const subOptionRadios = document.querySelectorAll('input[name="sub_option"]');
    const detailGroup = document.getElementById('liDetailThresholdGroup');
    const detailThresholdInput = document.getElementById('liDetailThreshold');
    const detailThresholdVal = document.getElementById('liDetailThresholdVal');

    const nColorsInput = document.getElementById('liNColors');
    const nColorsVal = document.getElementById('liNColorsVal');

    const presetCards = document.querySelectorAll('#liSvgPresets .li-svg-preset-card');
    const presetInput = document.getElementById('liPresetInput');

    const useFullImageCheckbox = document.getElementById('liUseFullImage');
    const squareCanvasCheckbox = document.getElementById('liSquareCanvas');
    const hierarchicalCutoutCheckbox = document.getElementById('liHierarchicalCutout');
    const bgRadios = document.querySelectorAll('input[name="bg_color"]');

    const filterSpeckleInput = document.getElementById('liFilterSpeckle');
    const filterSpeckleVal = document.getElementById('liFilterSpeckleVal');
    const cornerThresholdInput = document.getElementById('liCornerThreshold');
    const cornerThresholdVal = document.getElementById('liCornerThresholdVal');
    const spliceThresholdInput = document.getElementById('liSpliceThreshold');
    const spliceThresholdVal = document.getElementById('liSpliceThresholdVal');
    const curveModeSelect = document.getElementById('liCurveMode');

    const reTraceBtn = document.getElementById('liSvgReTraceBtn');
    const saveBtn = document.getElementById('liSvgSaveBtn');

    // Live Recoloring & Swatch State
    let originalPalette = [];
    let paletteMap = {}; // index -> newColor (or null for transparent)
    let undoStack = [];
    let selectedPaletteIndex = null;

    // Initialize originalPalette from existing swatches in DOM
    const initialSwatches = document.querySelectorAll('.li-svg-swatch');
    initialSwatches.forEach(swatch => {
        const orig = swatch.dataset.originalColor;
        if (orig) originalPalette.push(orig);
    });

    // Swatch editor elements
    const swatchEditorDrawer = document.getElementById('liSwatchEditorDrawer');
    const editSwatchName = document.getElementById('liEditSwatchName');
    const editSwatchHex = document.getElementById('liEditSwatchHex');
    const editKeepOriginalBtn = document.getElementById('liEditKeepOriginalBtn');
    const editColorPicker = document.getElementById('liEditColorPicker');
    const editSetMonoBtn = document.getElementById('liEditSetMonoBtn');
    const editMakeTransBtn = document.getElementById('liEditMakeTransBtn');

    const undoPaletteBtn = document.getElementById('liUndoPaletteBtn');
    const resetPaletteBtn = document.getElementById('liResetPaletteBtn');
    const removeNearWhiteBtn = document.getElementById('liRemoveNearWhiteBtn');

    // Push state for Undo
    function pushUndoState() {
        undoStack.push(JSON.parse(JSON.stringify(paletteMap)));
        if (undoPaletteBtn) undoPaletteBtn.disabled = false;
    }

    // Sliders live text binding
    if (detailThresholdInput && detailThresholdVal) {
        detailThresholdInput.addEventListener('input', () => {
            detailThresholdVal.textContent = detailThresholdInput.value;
        });
    }
    if (nColorsInput && nColorsVal) {
        nColorsInput.addEventListener('input', () => {
            nColorsVal.textContent = `${nColorsInput.value} colours`;
        });
    }
    if (filterSpeckleInput && filterSpeckleVal) {
        filterSpeckleInput.addEventListener('input', () => {
            filterSpeckleVal.textContent = `${filterSpeckleInput.value} px`;
        });
    }
    if (cornerThresholdInput && cornerThresholdVal) {
        cornerThresholdInput.addEventListener('input', () => {
            cornerThresholdVal.textContent = `${cornerThresholdInput.value}°`;
        });
    }
    if (spliceThresholdInput && spliceThresholdVal) {
        spliceThresholdInput.addEventListener('input', () => {
            spliceThresholdVal.textContent = `${spliceThresholdInput.value}°`;
        });
    }
    if (monoColorInput && monoColorVal) {
        monoColorInput.addEventListener('input', () => {
            monoColorVal.textContent = monoColorInput.value;
        });
    }
    if (hybridMonoColorInput && hybridMonoColorVal) {
        hybridMonoColorInput.addEventListener('input', () => {
            hybridMonoColorVal.textContent = hybridMonoColorInput.value;
        });
    }

    // Sub-option change (silhouette vs detail)
    subOptionRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (radio.checked && detailGroup) {
                detailGroup.style.display = (radio.value === 'detail') ? 'block' : 'none';
            }
        });
    });

    // Mode switching
    modeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            modeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const mode = btn.dataset.mode;
            colorModeInput.value = mode;

            const paletteBar = document.getElementById('liSvgPaletteBar');
            if (mode === 'monochrome') {
                if (monoControls) monoControls.style.display = 'block';
                if (colorControls) colorControls.style.display = 'none';
                if (hybridMonoGroup) hybridMonoGroup.style.display = 'none';
                if (paletteBar) paletteBar.style.display = 'none';
            } else if (mode === 'hybrid') {
                if (monoControls) monoControls.style.display = 'none';
                if (colorControls) colorControls.style.display = 'block';
                if (hybridMonoGroup) hybridMonoGroup.style.display = 'block';
                if (paletteBar) paletteBar.style.display = 'block';
            } else {
                if (monoControls) monoControls.style.display = 'none';
                if (colorControls) colorControls.style.display = 'block';
                if (hybridMonoGroup) hybridMonoGroup.style.display = 'none';
                if (paletteBar) paletteBar.style.display = 'block';
            }
        });
    });

    // Preset switching
    presetCards.forEach(card => {
        card.addEventListener('click', () => {
            presetCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            if (presetInput) {
                presetInput.value = card.dataset.preset;
            }
        });
    });

    // Viewport Size Switcher
    const sizeBtns = document.querySelectorAll('.li-svg-size-btn');
    sizeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            sizeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const sz = btn.dataset.size;
            if (!svgObject) return;
            if (sz === 'fit') {
                svgObject.style.width = '100%';
                svgObject.style.height = 'auto';
            } else {
                svgObject.style.width = `${sz}px`;
                svgObject.style.height = `${sz}px`;
            }
        });
    });

    // Viewport Background Switcher
    const bgBtns = document.querySelectorAll('[data-svg-bg]');
    bgBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            bgBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const bg = btn.dataset.svgBg;
            if (svgViewport) {
                svgViewport.className = `li-svg-viewport-wrapper bg-${bg}`;
            }
        });
    });

    // =========================================================================
    // 3. SVG DOM INTERACTION & LIVE RECOLORING
    // =========================================================================

    function attachSvgEventListeners() {
        if (!svgObject) return;
        try {
            const svgDoc = svgObject.contentDocument;
            if (!svgDoc) return;

            // Inject interactive style into preview SVG
            let style = svgDoc.getElementById('liPreviewInteractiveStyle');
            if (!style) {
                style = svgDoc.createElementNS('http://www.w3.org/2000/svg', 'style');
                style.id = 'liPreviewInteractiveStyle';
                style.textContent = `
                    [data-palette-index] {
                        cursor: pointer !important;
                        transition: opacity 0.12s ease;
                    }
                    [data-palette-index]:hover {
                        opacity: 0.85;
                        outline: 2px dashed #6366f1;
                    }
                    [data-palette-index].li-highlighted {
                        outline: 3px solid #6366f1;
                    }
                `;
                svgDoc.documentElement.appendChild(style);
            }

            const paths = svgDoc.querySelectorAll('[data-palette-index]');
            paths.forEach(path => {
                path.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const pIdx = path.getAttribute('data-palette-index');
                    if (pIdx !== null) {
                        selectSwatch(parseInt(pIdx, 10));
                    }
                });
            });

            // Re-apply any active paletteMap
            updateSvgDomFills();
        } catch (e) {
            console.warn("Could not attach click listeners to SVG object:", e);
        }
    }

    if (svgObject) {
        svgObject.addEventListener('load', attachSvgEventListeners);
        // Try immediately in case it is already loaded
        attachSvgEventListeners();
    }

    function updateSvgDomFills() {
        if (!svgObject) return;
        try {
            const svgDoc = svgObject.contentDocument;
            if (!svgDoc) return;

            const paths = svgDoc.querySelectorAll('[data-palette-index]');
            paths.forEach(p => {
                const idx = parseInt(p.getAttribute('data-palette-index'), 10);
                if (idx in paletteMap) {
                    const col = paletteMap[idx];
                    if (col === null || col === 'none' || col === 'transparent') {
                        p.style.display = 'none';
                    } else {
                        p.style.display = '';
                        p.setAttribute('fill', col);
                    }
                } else {
                    p.style.display = '';
                    const orig = originalPalette[idx];
                    if (orig) p.setAttribute('fill', orig);
                }
            });
        } catch (e) {
            console.warn("Could not update SVG DOM fills:", e);
        }
    }

    function selectSwatch(idx) {
        selectedPaletteIndex = idx;

        // Highlight selected swatch in UI
        const allSwatches = document.querySelectorAll('.li-svg-swatch');
        allSwatches.forEach(s => {
            const sIdx = parseInt(s.dataset.paletteIndex, 10);
            s.classList.toggle('active', sIdx === idx);
        });

        // Highlight paths in SVG object
        try {
            const svgDoc = svgObject ? svgObject.contentDocument : null;
            if (svgDoc) {
                const paths = svgDoc.querySelectorAll('[data-palette-index]');
                paths.forEach(p => {
                    const pIdx = parseInt(p.getAttribute('data-palette-index'), 10);
                    p.classList.toggle('li-highlighted', pIdx === idx);
                });
            }
        } catch (e) {
            // Ignore cross-doc error
        }

        // Open editor drawer
        if (swatchEditorDrawer) {
            swatchEditorDrawer.style.display = 'flex';
            if (editSwatchName) editSwatchName.textContent = `Colour #${idx + 1}`;
            const currentColor = (idx in paletteMap) ? paletteMap[idx] : originalPalette[idx];
            if (editSwatchHex) editSwatchHex.textContent = currentColor || 'Transparent';
            if (editColorPicker && currentColor && currentColor.startsWith('#')) {
                editColorPicker.value = currentColor;
            }
        }
    }

    function applyLiveColor(idx, newColor) {
        pushUndoState();

        if (newColor === null || newColor === 'transparent' || newColor === 'none') {
            paletteMap[idx] = null;
        } else {
            paletteMap[idx] = newColor;
        }

        updateSvgDomFills();
        updateSwatchUI(idx, newColor);
    }

    function updateSwatchUI(idx, newColor) {
        const swatch = document.querySelector(`.li-svg-swatch[data-palette-index="${idx}"]`);
        if (!swatch) return;

        const colBox = swatch.querySelector('.li-svg-swatch-color');
        const label = swatch.querySelector('.li-svg-swatch-label');
        const picker = swatch.querySelector('.li-svg-swatch-picker');

        if (newColor === null) {
            swatch.classList.add('is-transparent');
            if (colBox) colBox.style.backgroundColor = 'transparent';
            if (label) label.textContent = 'None';
            if (selectedPaletteIndex === idx && editSwatchHex) editSwatchHex.textContent = 'Transparent';
        } else {
            swatch.classList.remove('is-transparent');
            if (colBox) colBox.style.backgroundColor = newColor;
            if (label) label.textContent = newColor;
            if (picker) picker.value = newColor;
            if (selectedPaletteIndex === idx && editSwatchHex) editSwatchHex.textContent = newColor;
        }
    }

    function bindSwatchEvents(swatch) {
        const idx = parseInt(swatch.dataset.paletteIndex, 10);

        swatch.addEventListener('click', (e) => {
            if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'button') {
                return;
            }
            selectSwatch(idx);
        });

        // Color picker inside swatch
        const picker = swatch.querySelector('.li-svg-swatch-picker');
        if (picker) {
            picker.addEventListener('input', () => {
                applyLiveColor(idx, picker.value);
            });
        }

        // Quick Mono button
        const monoBtn = swatch.querySelector('.li-swatch-mono-btn');
        if (monoBtn) {
            monoBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const monoCol = (monoColorInput ? monoColorInput.value : '#000000') || '#000000';
                applyLiveColor(idx, monoCol);
            });
        }

        // Quick Transparent button
        const removeBtn = swatch.querySelector('.li-swatch-remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                applyLiveColor(idx, null);
            });
        }
    }

    // Bind existing swatches on load
    initialSwatches.forEach(bindSwatchEvents);

    // Editor drawer buttons
    if (editKeepOriginalBtn) {
        editKeepOriginalBtn.addEventListener('click', () => {
            if (selectedPaletteIndex === null) return;
            const orig = originalPalette[selectedPaletteIndex];
            if (orig) applyLiveColor(selectedPaletteIndex, orig);
        });
    }

    if (editColorPicker) {
        editColorPicker.addEventListener('input', () => {
            if (selectedPaletteIndex === null) return;
            applyLiveColor(selectedPaletteIndex, editColorPicker.value);
        });
    }

    if (editSetMonoBtn) {
        editSetMonoBtn.addEventListener('click', () => {
            if (selectedPaletteIndex === null) return;
            const monoCol = (monoColorInput ? monoColorInput.value : '#000000') || '#000000';
            applyLiveColor(selectedPaletteIndex, monoCol);
        });
    }

    if (editMakeTransBtn) {
        editMakeTransBtn.addEventListener('click', () => {
            if (selectedPaletteIndex === null) return;
            applyLiveColor(selectedPaletteIndex, null);
        });
    }

    // Undo action
    if (undoPaletteBtn) {
        undoPaletteBtn.addEventListener('click', () => {
            if (undoStack.length === 0) return;
            paletteMap = undoStack.pop();
            if (undoStack.length === 0) undoPaletteBtn.disabled = true;

            updateSvgDomFills();
            originalPalette.forEach((orig, idx) => {
                const col = (idx in paletteMap) ? paletteMap[idx] : orig;
                updateSwatchUI(idx, col);
            });
        });
    }

    // Reset to Original
    if (resetPaletteBtn) {
        resetPaletteBtn.addEventListener('click', () => {
            pushUndoState();
            paletteMap = {};
            updateSvgDomFills();
            originalPalette.forEach((orig, idx) => {
                updateSwatchUI(idx, orig);
            });
            if (selectedPaletteIndex !== null) {
                selectSwatch(selectedPaletteIndex);
            }
        });
    }

    // Remove Near-White
    if (removeNearWhiteBtn) {
        removeNearWhiteBtn.addEventListener('click', () => {
            pushUndoState();
            originalPalette.forEach((orig, idx) => {
                const current = (idx in paletteMap) ? paletteMap[idx] : orig;
                if (current && isNearWhite(current)) {
                    paletteMap[idx] = null;
                    updateSwatchUI(idx, null);
                }
            });
            updateSvgDomFills();
        });
    }

    // =========================================================================
    // 4. STATUS POLLING ENGINE
    // =========================================================================
    let pollInterval = null;

    function startStatusPolling() {
        if (pollInterval) clearInterval(pollInterval);
        if (processingBanner) processingBanner.style.display = 'flex';
        if (reTraceBtn) {
            reTraceBtn.disabled = true;
            reTraceBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Vectorizing...';
        }

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(statusUrl, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                if (!res.ok) return;
                const data = await res.json();

                if (statusHeading) statusHeading.textContent = data.queue_text || "Processing Vector Paths...";

                if (data.status === 'done') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    if (processingBanner) processingBanner.style.display = 'none';
                    if (reTraceBtn) {
                        reTraceBtn.disabled = false;
                        reTraceBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Update Vector (Trace)';
                    }

                    // Hide placeholder and reload SVG object
                    const placeholder = document.getElementById('liSvgPlaceholder');
                    if (placeholder) placeholder.style.display = 'none';

                    let currentSvgObj = document.getElementById('liSvgObject');
                    if (!currentSvgObj && svgViewport) {
                        currentSvgObj = document.createElement('object');
                        currentSvgObj.id = 'liSvgObject';
                        currentSvgObj.type = 'image/svg+xml';
                        currentSvgObj.className = 'li-svg-object';
                        currentSvgObj.style.width = '512px';
                        currentSvgObj.style.height = '512px';
                        svgViewport.appendChild(currentSvgObj);
                    }
                    if (currentSvgObj) {
                        currentSvgObj.style.display = 'block';
                        const timestamp = new Date().getTime();
                        currentSvgObj.data = `${previewUrl}?t=${timestamp}`;
                        currentSvgObj.onload = () => {
                            attachSvgEventListeners();
                            syncPreviewWithCurrentPalette();
                        };
                    }

                    // Update stats
                    const stats = data.svg_stats || {};
                    if (statPaths) statPaths.textContent = stats.path_count || 0;
                    if (statColors) statColors.textContent = stats.color_count || 0;
                    if (statSize) statSize.textContent = stats.file_size_formatted || '0 KB';
                    if (sizeWarnAlert) {
                        sizeWarnAlert.style.display = stats.warn_large ? 'flex' : 'none';
                    }

                    // Re-render palette swatches if provided
                    if (data.palette && Array.isArray(data.palette) && data.palette.length > 0) {
                        renderPaletteSwatches(data.palette);
                    }
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    if (processingBanner) processingBanner.style.display = 'none';
                    if (reTraceBtn) {
                        reTraceBtn.disabled = false;
                        reTraceBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Update Vector (Trace)';
                    }
                    if (errorAlert && errorMessage) {
                        errorMessage.textContent = data.error_message || "Vectorization failed.";
                        errorAlert.style.display = 'flex';
                    }
                }
            } catch (err) {
                console.error("Status polling error:", err);
            }
        }, 1000);
    }

    const initialStatus = document.getElementById('liJobStatus').value;
    if (initialStatus === 'queued' || initialStatus === 'processing') {
        startStatusPolling();
    }

    // Re-trace (Render) submission
    if (reTraceBtn) {
        reTraceBtn.addEventListener('click', async () => {
            if (errorAlert) errorAlert.style.display = 'none';

            let selectedSubOption = 'silhouette';
            subOptionRadios.forEach(r => { if (r.checked) selectedSubOption = r.value; });

            let selectedBg = 'transparent';
            bgRadios.forEach(r => { if (r.checked) selectedBg = r.value; });

            const payload = {
                color_mode: colorModeInput ? colorModeInput.value : 'monochrome',
                sub_option: selectedSubOption,
                color: monoColorInput ? monoColorInput.value : '#000000',
                detail_threshold: detailThresholdInput ? parseInt(detailThresholdInput.value, 10) : 128,
                n_colors: nColorsInput ? parseInt(nColorsInput.value, 10) : 8,
                monochrome_color: hybridMonoColorInput ? hybridMonoColorInput.value : '#000000',
                preset: presetInput ? presetInput.value : 'balanced',
                hierarchical: (hierarchicalCutoutCheckbox && hierarchicalCutoutCheckbox.checked) ? 'cutout' : 'stacked',
                use_full_image: useFullImageCheckbox ? useFullImageCheckbox.checked : false,
                square_canvas: squareCanvasCheckbox ? squareCanvasCheckbox.checked : false,
                bg_color: selectedBg,
                mode: curveModeSelect ? curveModeSelect.value : 'spline',
                custom_params: {
                    filter_speckle: filterSpeckleInput ? parseInt(filterSpeckleInput.value, 10) : 4,
                    corner_threshold: cornerThresholdInput ? parseInt(cornerThresholdInput.value, 10) : 50,
                    splice_threshold: spliceThresholdInput ? parseInt(spliceThresholdInput.value, 10) : 45,
                }
            };

            try {
                const res = await fetch(renderUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload)
                });
                const resData = await res.json();
                if (resData.success) {
                    startStatusPolling();
                } else {
                    if (errorAlert && errorMessage) {
                        errorMessage.textContent = resData.error || "Failed to start tracing.";
                        errorAlert.style.display = 'flex';
                    }
                }
            } catch (err) {
                console.error("Render submission error:", err);
            }
        });
    }

    // =========================================================================
    // 5. SAVE SVG WITH SERVER RECOLOR SYNC AND AUTOMATIC CLEANUP
    // =========================================================================
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving SVG...';

            try {
                // 1. If any live palette modifications exist, sync them to server before download
                if (recolorUrl && Object.keys(paletteMap).length > 0) {
                    await fetch(recolorUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: JSON.stringify({ palette_map: paletteMap })
                    });
                }

                // 2. Fetch SVG blob from server with attachment headers
                const res = await fetch(downloadUrl);
                if (!res.ok) throw new Error("Could not download SVG file.");
                const blob = await res.blob();

                // 3. Trigger client download
                const downloadLink = document.createElement('a');
                const objectUrl = URL.createObjectURL(blob);
                downloadLink.href = objectUrl;
                downloadLink.download = `listimage-${jobId.substring(0, 8)}.svg`;
                document.body.appendChild(downloadLink);
                downloadLink.click();
                document.body.removeChild(downloadLink);
                URL.revokeObjectURL(objectUrl);

                // 4. POST to cleanup endpoint which deletes workspace and DB record, then redirects to index
                const cleanupRes = await fetch(cleanupUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                const cleanupData = await cleanupRes.json();
                window.location.href = cleanupData.redirect_url || '/listimage/';
            } catch (err) {
                console.error("Save SVG error:", err);
                alert("Failed to download SVG file.");
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save SVG';
            }
        });
    }

    // Render palette swatches dynamically on trace completion
    function renderPaletteSwatches(palette) {
        const swatchesGrid = document.getElementById('liSwatchesGrid');
        const paletteBar = document.getElementById('liSvgPaletteBar');
        if (!swatchesGrid || !paletteBar) return;

        originalPalette = [...palette];
        paletteMap = {};
        undoStack = [];
        if (undoPaletteBtn) undoPaletteBtn.disabled = true;
        if (swatchEditorDrawer) swatchEditorDrawer.style.display = 'none';

        swatchesGrid.innerHTML = '';
        palette.forEach((hex, idx) => {
            const swatch = document.createElement('div');
            swatch.className = 'li-svg-swatch';
            swatch.dataset.paletteIndex = idx;
            swatch.dataset.originalColor = hex;
            swatch.tabIndex = 0;
            swatch.setAttribute('role', 'button');
            swatch.setAttribute('aria-label', `Palette colour ${idx}`);

            const colBox = document.createElement('div');
            colBox.className = 'li-svg-swatch-color';
            colBox.style.backgroundColor = hex;

            const label = document.createElement('span');
            label.className = 'li-svg-swatch-label';
            label.textContent = hex;

            const picker = document.createElement('input');
            picker.type = 'color';
            picker.className = 'li-svg-swatch-picker';
            picker.value = hex;
            picker.title = 'Change colour';

            const monoBtn = document.createElement('button');
            monoBtn.type = 'button';
            monoBtn.className = 'li-svg-swatch-btn li-swatch-mono-btn';
            monoBtn.title = 'Set to monochrome';
            monoBtn.innerHTML = '&bull; Mono';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'li-svg-swatch-btn li-swatch-remove-btn';
            removeBtn.title = 'Make transparent';
            removeBtn.innerHTML = '&times;';

            swatch.appendChild(colBox);
            swatch.appendChild(label);
            swatch.appendChild(picker);
            swatch.appendChild(monoBtn);
            swatch.appendChild(removeBtn);

            bindSwatchEvents(swatch);
            swatchesGrid.appendChild(swatch);
        });

        const currentMode = colorModeInput ? colorModeInput.value : 'monochrome';
        paletteBar.style.display = (currentMode === 'monochrome') ? 'none' : 'block';
    }
});
