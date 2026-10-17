/**
 * DocEdit - Document Editor Frontend Application
 * project-h
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const dropzone = document.getElementById('doceditDropzone');
    const fileInput = document.getElementById('doceditFileInput');
    const ocrLangSelect = document.getElementById('doceditOcrLang');
    const workspace = document.getElementById('doceditWorkspace');
    const editorPaper = document.getElementById('doceditPaper');
    const noticeBanner = document.getElementById('doceditNoticeBanner');
    const noticeTitle = document.getElementById('doceditNoticeTitle');
    const noticeNote = document.getElementById('doceditNoticeNote');

    // Pan (Side Panel) Elements
    const panProgressBar = document.getElementById('panProgressBar');
    const panProgressText = document.getElementById('panProgressText');
    const panProgressPercent = document.getElementById('panProgressPercent');
    const panFilename = document.getElementById('panFilename');
    const panExtension = document.getElementById('panExtension');
    const panFilesize = document.getElementById('panFilesize');
    const panPages = document.getElementById('panPages');
    const panWords = document.getElementById('panWords');
    const panChars = document.getElementById('panChars');
    const panFontName = document.getElementById('panFontName');
    const panFontSize = document.getElementById('panFontSize');
    const panFontBadge = document.getElementById('panFontBadge');
    const panAltBox = document.getElementById('panAltBox');
    const panAltText = document.getElementById('panAltText');
    const panFuzzyCount = document.getElementById('panFuzzyCount');
    const panFuzzyList = document.getElementById('panFuzzyList');
    const panBtnDownload = document.getElementById('panBtnDownload');
    const panBtnCancel = document.getElementById('panBtnCancel');

    // Toolbar Elements
    const tbFontSelect = document.getElementById('tbFontSelect');
    const tbFontRefresh = document.getElementById('tbFontRefresh');
    const tbInstallFontBtn = document.getElementById('tbInstallFontBtn');
    const tbFontSizeSelect = document.getElementById('tbFontSizeSelect');
    const tbFuzzyToggle = document.getElementById('tbFuzzyToggle');
    const tbAutoSaveIndicator = document.getElementById('tbAutoSaveIndicator');
    const tbAutoSaveIcon = document.getElementById('tbAutoSaveIcon');
    const tbAutoSaveText = document.getElementById('tbAutoSaveText');
    const panAutoSaveStatus = document.getElementById('panAutoSaveStatus');

    // Font Installation Modal Elements
    const installFontModal = document.getElementById('doceditInstallFontModal');
    const modalBtnCloseFontInstall = document.getElementById('modalBtnCloseFontInstall');
    const modalBtnSubmitFontInstall = document.getElementById('modalBtnSubmitFontInstall');
    const tabBtnFontFile = document.getElementById('tabBtnFontFile');
    const tabBtnFontOnline = document.getElementById('tabBtnFontOnline');
    const tabContentFontFile = document.getElementById('tabContentFontFile');
    const tabContentFontOnline = document.getElementById('tabContentFontOnline');
    const fontFileDropzone = document.getElementById('fontFileDropzone');
    const fontFileInput = document.getElementById('fontFileInput');
    const selectedFontFileName = document.getElementById('selectedFontFileName');
    const fontSearchInput = document.getElementById('fontSearchInput');
    const fontInstallStatus = document.getElementById('fontInstallStatus');
    let selectedFontFile = null;
    let activeInstallTab = 'file';

    // Confirmation Modal Elements
    const confirmModal = document.getElementById('doceditConfirmModal');
    const modalBtnConfirm = document.getElementById('modalBtnConfirm');
    const modalBtnKeepEditing = document.getElementById('modalBtnKeepEditing');

    // Download Format Elements
    const panDownloadFormat = document.getElementById('panDownloadFormat');
    const modalDownloadFormat = document.getElementById('modalDownloadFormat');
    const panOptOriginal = document.getElementById('panOptOriginal');
    const modalOptOriginal = document.getElementById('modalOptOriginal');

    // Table & Line Elements
    const tbInsertTable = document.getElementById('tbInsertTable');
    const tbAddRow = document.getElementById('tbAddRow');
    const tbInsertLine = document.getElementById('tbInsertLine');

    // Multi-page Navigation & Zoom Elements
    const tbPageNavGroup = document.getElementById('tbPageNavGroup');
    const tbPageSep = document.getElementById('tbPageSep');
    const tbPagePrev = document.getElementById('tbPagePrev');
    const tbPageNext = document.getElementById('tbPageNext');
    const tbPageIndicator = document.getElementById('tbPageIndicator');
    const tbZoomOut = document.getElementById('tbZoomOut');
    const tbZoomIn = document.getElementById('tbZoomIn');
    const tbZoomLevel = document.getElementById('tbZoomLevel');

    // Layout Alignment & Nudge Elements
    const tbLayoutAlignSep = document.getElementById('tbLayoutAlignSep');
    const tbLayoutAlignGroup = document.getElementById('tbLayoutAlignGroup');
    const tbAlignBlockLeft = document.getElementById('tbAlignBlockLeft');
    const tbNudgeLeft = document.getElementById('tbNudgeLeft');
    const tbNudgeRight = document.getElementById('tbNudgeRight');
    const tbNudgeUp = document.getElementById('tbNudgeUp');
    const tbNudgeDown = document.getElementById('tbNudgeDown');
    const tbBtnBold = document.querySelector('.tb-btn[data-cmd="bold"]');
    const tbBtnItalic = document.querySelector('.tb-btn[data-cmd="italic"]');
    const tbBtnUnderline = document.querySelector('.tb-btn[data-cmd="underline"]');

    // State
    let currentSessionId = null;
    let pollInterval = null;
    let currentMeta = null;
    let showFuzzyHighlights = true;
    let currentMode = 'flow'; // 'flow' or 'layout_preserved'
    let currentPagesData = [];
    let currentPageIndex = 1;
    let currentZoom = 100;

    // Active block tracking for layout-preserved mode
    let activeBlockEl = null;
    let activeBlockData = null;
    let activeBlockPage = null;
    let floatingBlockToolbar = null;


    // Helper: Format bytes
    function formatBytes(bytes, decimals = 1) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // Helper: CSRF token
    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    // Notice banner helper
    function showNotice(title, note) {
        noticeTitle.textContent = title;
        noticeNote.textContent = note;
        noticeBanner.classList.add('show');
        noticeBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hideNotice() {
        noticeBanner.classList.remove('show');
    }

    // Check if redirected to /docedit/ after successful save & download
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const hasDownloadQuery = urlParams.get('downloaded') === '1';
        let hasDownloadStorage = false;
        if (sessionStorage.getItem('docedit_download_success') === '1') {
            hasDownloadStorage = true;
            sessionStorage.removeItem('docedit_download_success');
        }

        if (hasDownloadQuery || hasDownloadStorage) {
            showNotice(
                'Document downloaded successfully to your system!',
                'Note: This file has not been permanently saved on the server. Please keep your downloaded copy in your desired folder.'
            );
            if (hasDownloadQuery) {
                const cleanUrl = window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
            }
        }
    } catch (e) {
        console.warn('Could not check download notification status:', e);
    }

    // --------------------------------------------------------------------------
    // Real-Time Auto-Save Engine
    // --------------------------------------------------------------------------
    let autoSaveTimeout = null;
    let isAutoSaving = false;

    function setAutoSaveStatus(status) {
        if (tbAutoSaveIndicator) {
            if (status === 'saving') {
                tbAutoSaveIndicator.style.background = 'rgba(234, 179, 8, 0.15)';
                tbAutoSaveIndicator.style.color = '#ca8a04';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-arrows-rotate fa-spin';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Saving...';
            } else if (status === 'saved') {
                tbAutoSaveIndicator.style.background = 'rgba(16, 185, 129, 0.12)';
                tbAutoSaveIndicator.style.color = '#059669';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-cloud-arrow-up';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Saved';
            } else if (status === 'modified') {
                tbAutoSaveIndicator.style.background = 'rgba(59, 130, 246, 0.12)';
                tbAutoSaveIndicator.style.color = '#2563eb';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-pen-to-square';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Unsaved changes';
            } else if (status === 'error') {
                tbAutoSaveIndicator.style.background = 'rgba(239, 68, 68, 0.15)';
                tbAutoSaveIndicator.style.color = '#dc2626';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-triangle-exclamation';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Save error';
            }
        }
        if (panAutoSaveStatus) {
            if (status === 'saving') {
                panAutoSaveStatus.style.background = 'rgba(234, 179, 8, 0.18)';
                panAutoSaveStatus.style.color = '#b45309';
                panAutoSaveStatus.style.borderColor = 'rgba(234, 179, 8, 0.35)';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-arrows-rotate fa-spin"></i> Auto-saving...';
            } else if (status === 'saved') {
                panAutoSaveStatus.style.background = 'rgba(16, 185, 129, 0.15)';
                panAutoSaveStatus.style.color = '#059669';
                panAutoSaveStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> All changes saved';
            } else if (status === 'modified') {
                panAutoSaveStatus.style.background = 'rgba(59, 130, 246, 0.15)';
                panAutoSaveStatus.style.color = '#1d4ed8';
                panAutoSaveStatus.style.borderColor = 'rgba(59, 130, 246, 0.3)';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Editing...';
            } else if (status === 'error') {
                panAutoSaveStatus.style.background = 'rgba(239, 68, 68, 0.15)';
                panAutoSaveStatus.style.color = '#b91c1c';
                panAutoSaveStatus.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Save error';
            }
        }
    }

    function syncBlocksFromDom() {
        if (currentMode !== 'layout_preserved' || !currentPagesData || currentPagesData.length === 0) return;
        currentPagesData.forEach(p => {
            if (!p.blocks) return;
            p.blocks.forEach(b => {
                const el = document.querySelector(`.docedit-text-block[data-block-id="${b.id}"]`);
                if (!el) return;
                const newText = el.innerText.trim();
                if (newText !== b.text) {
                    b.text = newText;
                    b.is_modified = true;
                }
                if (el.style.fontFamily) {
                    const cleanFont = el.style.fontFamily.replace(/['",]/g, '').replace(/\s*(serif|sans-serif|monospace)\s*$/i, '').trim();
                    if (cleanFont && cleanFont !== b.font_name) {
                        b.font_name = cleanFont;
                        b.is_modified = true;
                    }
                }
                if (el.style.fontSize) {
                    const parsedSize = parseFloat(el.style.fontSize);
                    if (!isNaN(parsedSize) && Math.abs(parsedSize - (b.font_size_pt || 12)) > 0.1) {
                        b.font_size_pt = parsedSize;
                        b.is_modified = true;
                    }
                }
                const curL = parseFloat(el.style.left);
                const curT = parseFloat(el.style.top);
                if (!isNaN(curL) && Math.abs(curL - b.left_pct) > 0.001) {
                    b.left_pct = Math.round(curL * 1000) / 1000;
                    b.is_modified = true;
                }
                if (!isNaN(curT) && Math.abs(curT - b.top_pct) > 0.001) {
                    b.top_pct = Math.round(curT * 1000) / 1000;
                    b.is_modified = true;
                }
                if (el.style.fontWeight === 'bold' || parseInt(el.style.fontWeight, 10) >= 600) {
                    if (!b.is_bold) { b.is_bold = true; b.is_modified = true; }
                } else if (el.style.fontWeight === 'normal') {
                    if (b.is_bold) { b.is_bold = false; b.is_modified = true; }
                }
                if (el.style.fontStyle === 'italic') {
                    if (!b.is_italic) { b.is_italic = true; b.is_modified = true; }
                } else if (el.style.fontStyle === 'normal') {
                    if (b.is_italic) { b.is_italic = false; b.is_modified = true; }
                }
                if (el.style.textDecoration && el.style.textDecoration.includes('underline')) {
                    if (!b.is_underline) { b.is_underline = true; b.is_modified = true; }
                } else if (el.style.textDecoration === 'none') {
                    if (b.is_underline) { b.is_underline = false; b.is_modified = true; }
                }

                // Recalculate bbox from current left_pct, top_pct, width_pct, height_pct
                const lx0 = (b.left_pct / 100.0) * p.width;
                const ly0 = (b.top_pct / 100.0) * p.height;
                const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
                const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
                b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];
            });
        });
    }

    function triggerAutoSave(delayMs = 600) {
        if (!currentSessionId) return;
        setAutoSaveStatus('modified');
        if (autoSaveTimeout) {
            clearTimeout(autoSaveTimeout);
        }
        autoSaveTimeout = setTimeout(async () => {
            if (!currentSessionId || isAutoSaving) return;
            isAutoSaving = true;
            setAutoSaveStatus('saving');
            try {
                syncBlocksFromDom();
                const fontName = tbFontSelect ? tbFontSelect.value : (panFontName.textContent || 'EB Garamond');
                const fontSize = tbFontSizeSelect ? parseFloat(tbFontSizeSelect.value) : 12;
                const chosenFormat = (panDownloadFormat ? panDownloadFormat.value : 'pdf') || 'pdf';

                const payload = {
                    is_autosave: true,
                    font_name: fontName,
                    font_size_pt: fontSize,
                    export_format: chosenFormat,
                    html_content: editorPaper.innerHTML,
                };
                if (currentMode === 'layout_preserved' && currentPagesData && currentPagesData.length > 0) {
                    payload.pages_data = currentPagesData;
                }

                const resp = await fetch(`/docedit/api/save/${currentSessionId}/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify(payload),
                });
                const resData = await resp.json();
                if (resData.success) {
                    setAutoSaveStatus('saved');
                } else {
                    setAutoSaveStatus('error');
                }
            } catch (err) {
                console.warn('Auto-save error:', err);
                setAutoSaveStatus('error');
            } finally {
                isAutoSaving = false;
            }
        }, delayMs);
    }

    // --------------------------------------------------------------------------
    // Upload Handling
    // --------------------------------------------------------------------------
    if (dropzone && fileInput) {
        dropzone.addEventListener('click', (e) => {
            if (e.target !== ocrLangSelect && !e.target.closest('#doceditOcrLang')) {
                fileInput.click();
            }
        });

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('drag-over');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('drag-over');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('drag-over');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleFileUpload(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files.length > 0) {
                handleFileUpload(fileInput.files[0]);
            }
        });
    }

    async function handleFileUpload(file) {
        hideNotice();
        const formData = new FormData();
        formData.append('document', file);
        if (ocrLangSelect) {
            formData.append('ocr_lang', ocrLangSelect.value);
        }

        // Show workspace & progress immediately
        dropzone.style.display = 'none';
        workspace.classList.add('active');
        panProgressBar.style.width = '10%';
        panProgressPercent.textContent = '10%';
        panProgressText.textContent = 'Uploading document...';
        panFilename.textContent = file.name;
        const uploadExt = file.name.split('.').pop().toLowerCase();
        panExtension.textContent = '.' + uploadExt;
        panFilesize.textContent = formatBytes(file.size);

        // Update format options with original extension
        if (panOptOriginal) panOptOriginal.textContent = `Original Format (.${uploadExt})`;
        if (modalOptOriginal) modalOptOriginal.textContent = `Original Upload Format (.${uploadExt})`;

        // Default format selection based on uploaded document type
        if (['docx', 'pdf', 'txt', 'md', 'html'].includes(uploadExt)) {
            if (panDownloadFormat) panDownloadFormat.value = uploadExt;
            if (modalDownloadFormat) modalDownloadFormat.value = uploadExt;
        } else if (['png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'webp'].includes(uploadExt)) {
            // For scanned images, default to PDF or PNG
            if (panDownloadFormat) panDownloadFormat.value = 'pdf';
            if (modalDownloadFormat) modalDownloadFormat.value = 'pdf';
        }

        try {
            const resp = await fetch('/docedit/api/upload/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
                body: formData,
            });
            const data = await resp.json();
            if (!data.success) {
                alert('Upload error: ' + (data.error || 'Failed to upload document.'));
                resetWorkspace();
                return;
            }

            currentSessionId = data.session_id;
            startPollingStatus(currentSessionId);
        } catch (err) {
            console.error('Upload error:', err);
            alert('Upload failed: ' + err.message);
            resetWorkspace();
        }
    }

    // --------------------------------------------------------------------------
    // Status Polling & Side Pan Updating
    // --------------------------------------------------------------------------
    function startPollingStatus(sid) {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/docedit/api/status/${sid}/`);
                if (!resp.ok) return;
                const data = await resp.json();
                if (!data.success) return;

                updatePanFromStatus(data);

                if (data.status === 'ready' || data.is_editable) {
                    clearInterval(pollInterval);
                    loadDocumentIntoEditor(data);
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    alert('Error processing document: ' + (data.error || 'Unknown error'));
                    resetWorkspace();
                }
            } catch (err) {
                console.error('Polling error:', err);
            }
        }, 600);
    }

    function updatePanFromStatus(data) {
        currentMeta = data;
        const progress = data.progress || 0;
        panProgressBar.style.width = `${progress}%`;
        panProgressPercent.textContent = `${progress}%`;
        panProgressText.textContent = data.progress_message || 'Processing...';

        if (data.original_filename) panFilename.textContent = data.original_filename;
        if (data.extension) {
            const extLower = data.extension.toLowerCase();
            panExtension.textContent = '.' + extLower.toUpperCase();
            if (panOptOriginal) panOptOriginal.textContent = `Original Format (.${extLower})`;
            if (modalOptOriginal) modalOptOriginal.textContent = `Original Upload Format (.${extLower})`;
        }
        if (data.file_size) panFilesize.textContent = formatBytes(data.file_size);

        const stats = data.stats || {};
        panPages.textContent = stats.page_count || 1;
        panWords.textContent = stats.word_count || 0;
        panChars.textContent = stats.char_count || 0;

        const font = data.font_info || {};
        if (font.name) {
            panFontName.textContent = font.name;
            if (tbFontSelect) {
                ensureFontInSelect(font.name);
                tbFontSelect.value = font.name;
            }
        }
        if (font.size_pt) {
            panFontSize.textContent = `${font.size_pt} pt`;
            if (tbFontSizeSelect) {
                ensureFontSizeInSelect(font.size_pt);
                tbFontSizeSelect.value = String(font.size_pt);
            }
        }

        // Font Status Badge
        if (font.is_alternative) {
            panFontBadge.className = 'pan-badge badge-alternative';
            panFontBadge.textContent = 'Nearest Free Match';
            panAltBox.classList.add('show');
            panAltText.innerHTML = `Original font: <strong>${font.alternative_to || 'Unknown'}</strong>.<br>` +
                                   `Nearest match: <strong>${font.name}</strong> (${font.nearest_match_reason || 'Free equivalent'}).`;
        } else if (font.is_downloaded) {
            panFontBadge.className = 'pan-badge badge-downloaded';
            panFontBadge.textContent = 'Downloaded & Installed';
            panAltBox.classList.remove('show');
        } else if (font.is_system) {
            panFontBadge.className = 'pan-badge badge-system';
            panFontBadge.textContent = 'System Font';
            panAltBox.classList.remove('show');
        }

        // Fuzzy Words Review List
        const fuzzyList = data.fuzzy_words || [];
        panFuzzyCount.textContent = fuzzyList.length;
        panFuzzyList.innerHTML = '';
        if (fuzzyList.length > 0) {
            fuzzyList.slice(0, 25).forEach(fw => {
                const item = document.createElement('div');
                item.className = 'fuzzy-review-item';
                item.innerHTML = `<span>"${escapeHtml(fw.text)}"</span> <span class="fuzzy-conf-tag">${fw.conf}% conf</span>`;
                item.title = 'Click to jump to word in editor';
                item.addEventListener('click', () => jumpToFuzzyWord(fw.text));
                panFuzzyList.appendChild(item);
            });
        } else {
            panFuzzyList.innerHTML = '<div style="opacity:0.6; font-size:0.8rem; padding:0.3rem;">No suspicious fuzzy characters detected.</div>';
        }
    }

    function loadDocumentIntoEditor(data) {
        // Inject font CSS dynamically
        if (data.editor_font_css) {
            let styleTag = document.getElementById('doceditDynamicFontStyle');
            if (!styleTag) {
                styleTag = document.createElement('style');
                styleTag.id = 'doceditDynamicFontStyle';
                document.head.appendChild(styleTag);
            }
            styleTag.textContent = data.editor_font_css;
        }

        // Apply font to editor canvas
        const fontName = data.font_info && data.font_info.name ? data.font_info.name : 'EB Garamond';
        const fontSize = data.font_info && data.font_info.size_pt ? data.font_info.size_pt : 12;
        if (tbFontSelect) {
            ensureFontInSelect(fontName);
            tbFontSelect.value = fontName;
        }
        if (tbFontSizeSelect) {
            ensureFontSizeInSelect(fontSize);
            tbFontSizeSelect.value = String(fontSize);
        }
        editorPaper.style.fontFamily = `"${fontName}", serif`;
        editorPaper.style.fontSize = `${fontSize}pt`;

        if (data.is_layout_preserved && data.pages && data.pages.length > 0) {
            currentMode = 'layout_preserved';
            currentPagesData = data.pages;
            editorPaper.contentEditable = "false";
            if (tbPageNavGroup) tbPageNavGroup.style.display = 'inline-flex';
            if (tbPageSep) tbPageSep.style.display = 'inline-block';
            if (tbLayoutAlignSep) tbLayoutAlignSep.style.display = 'inline-block';
            if (tbLayoutAlignGroup) tbLayoutAlignGroup.style.display = 'inline-flex';
            currentPageIndex = 1;
            updatePageIndicator();
            renderLayoutPreservedPages(data.pages, fontName, fontSize);
        } else {
            currentMode = 'flow';
            currentPagesData = [];
            editorPaper.contentEditable = "true";
            if (tbPageNavGroup) tbPageNavGroup.style.display = 'none';
            if (tbPageSep) tbPageSep.style.display = 'none';
            if (tbLayoutAlignSep) tbLayoutAlignSep.style.display = 'none';
            if (tbLayoutAlignGroup) tbLayoutAlignGroup.style.display = 'none';
            if (data.document_html) {
                editorPaper.innerHTML = data.document_html;
            }
            attachFuzzyWordTooltips();
        }
    }

    function renderLayoutPreservedPages(pages, fontName, fontSize) {
        editorPaper.innerHTML = '';
        const pagesContainer = document.createElement('div');
        pagesContainer.className = 'docedit-pages-container';

        pages.forEach(p => {
            const sheet = document.createElement('div');
            sheet.className = 'docedit-page-sheet';
            sheet.id = `doceditPage_${p.page_num}`;
            sheet.setAttribute('data-page', p.page_num);

            const header = document.createElement('div');
            header.className = 'page-sheet-header';
            header.innerHTML = `
                <div class="page-sheet-badge">
                    <i class="fa-solid fa-file-invoice"></i> Page ${p.page_num} of ${pages.length}
                </div>
                <div class="page-sheet-dims">${Math.round(p.width)} × ${Math.round(p.height)} pt</div>
            `;

            const canvas = document.createElement('div');
            canvas.className = 'page-sheet-canvas';
            canvas.style.aspectRatio = `${p.width} / ${p.height}`;

            const bgImg = document.createElement('img');
            bgImg.className = 'page-bg-img';
            bgImg.src = p.image_url;
            bgImg.alt = `Page ${p.page_num}`;
            bgImg.draggable = false;

            const overlay = document.createElement('div');
            overlay.className = 'page-text-overlay';

            // Alignment guides for magnetic snapping
            const guideV = document.createElement('div');
            guideV.className = 'docedit-align-guide-v';
            const guideH = document.createElement('div');
            guideH.className = 'docedit-align-guide-h';

            p.blocks.forEach(b => {
                const blockDiv = document.createElement('div');
                blockDiv.className = `docedit-text-block${b.has_fuzzy ? ' has-fuzzy' : ''}`;
                blockDiv.contentEditable = 'true';
                blockDiv.spellcheck = false;
                blockDiv.setAttribute('data-block-id', b.id);
                blockDiv.setAttribute('data-page', p.page_num);
                blockDiv.style.left = `${b.left_pct}%`;
                blockDiv.style.top = `${b.top_pct}%`;
                blockDiv.style.minWidth = `${b.width_pct}%`;
                blockDiv.style.fontSize = `${b.font_size_pt || fontSize}pt`;
                blockDiv.style.fontFamily = `"${b.font_name || fontName}", serif`;
                if (b.is_bold) blockDiv.style.fontWeight = 'bold';
                if (b.is_italic) blockDiv.style.fontStyle = 'italic';
                if (b.is_underline) blockDiv.style.textDecoration = 'underline';
                blockDiv.textContent = b.text;

                blockDiv.addEventListener('focus', () => {
                    setActiveBlock(blockDiv, b, p);
                });

                blockDiv.addEventListener('click', (e) => {
                    setActiveBlock(blockDiv, b, p);
                });

                blockDiv.addEventListener('input', () => {
                    b.text = blockDiv.innerText.trim();
                    b.is_modified = true;
                    blockDiv.classList.add('is-edited');
                    updateFloatingToolbarPosition();
                    triggerAutoSave(700);
                });

                blockDiv.addEventListener('blur', () => {
                    blockDiv.classList.remove('is-focused');
                    if (b.is_modified) {
                        blockDiv.classList.add('is-edited');
                    }
                    triggerAutoSave(100);
                });

                blockDiv.addEventListener('keydown', (e) => {
                    // Formatting shortcuts
                    if (e.ctrlKey || e.metaKey) {
                        const k = e.key.toLowerCase();
                        if (k === 'b') {
                            e.preventDefault();
                            toggleActiveBlockBold();
                            return;
                        } else if (k === 'i') {
                            e.preventDefault();
                            toggleActiveBlockItalic();
                            return;
                        } else if (k === 'u') {
                            e.preventDefault();
                            toggleActiveBlockUnderline();
                            return;
                        }
                    }
                    // Alt + Arrow nudging & Alt + L snap
                    if (e.altKey) {
                        const step = e.shiftKey ? 0.5 : 0.1;
                        if (e.key === 'ArrowLeft') {
                            e.preventDefault();
                            nudgeActiveBlock(-step, 0);
                            return;
                        } else if (e.key === 'ArrowRight') {
                            e.preventDefault();
                            nudgeActiveBlock(step, 0);
                            return;
                        } else if (e.key === 'ArrowUp') {
                            e.preventDefault();
                            nudgeActiveBlock(0, -step);
                            return;
                        } else if (e.key === 'ArrowDown') {
                            e.preventDefault();
                            nudgeActiveBlock(0, step);
                            return;
                        } else if (e.key.toLowerCase() === 'l') {
                            e.preventDefault();
                            alignLeftWithNearestBlock();
                            return;
                        }
                    }
                });

                blockDiv.addEventListener('mousedown', (e) => {
                    if (e.altKey) {
                        e.preventDefault();
                        setActiveBlock(blockDiv, b, p);
                        startBlockDrag(e);
                    }
                });

                overlay.appendChild(blockDiv);
            });

            canvas.appendChild(bgImg);
            canvas.appendChild(overlay);
            canvas.appendChild(guideV);
            canvas.appendChild(guideH);
            sheet.appendChild(header);
            sheet.appendChild(canvas);
            pagesContainer.appendChild(sheet);
        });

        editorPaper.appendChild(pagesContainer);
        setupPageScrollObserver();
    }

    function setupPageScrollObserver() {
        const sheets = document.querySelectorAll('.docedit-page-sheet');
        if ('IntersectionObserver' in window && sheets.length > 0) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const pNum = parseInt(entry.target.getAttribute('data-page'), 10);
                        if (!isNaN(pNum)) {
                            currentPageIndex = pNum;
                            updatePageIndicator();
                        }
                    }
                });
            }, { threshold: 0.4 });

            sheets.forEach(s => observer.observe(s));
        }
    }

    function updatePageIndicator() {
        if (!tbPageIndicator) return;
        const total = currentPagesData.length || 1;
        tbPageIndicator.textContent = `Page ${currentPageIndex} / ${total}`;
    }

    // --------------------------------------------------------------------------
    // Active Block Management, Alignment & Formatting for Layout Preserved Mode
    // --------------------------------------------------------------------------
    function getOrCreateFloatingToolbar() {
        if (!floatingBlockToolbar) {
            floatingBlockToolbar = document.createElement('div');
            floatingBlockToolbar.className = 'docedit-block-toolbar';
            floatingBlockToolbar.contentEditable = 'false';
            floatingBlockToolbar.innerHTML = `
                <div class="block-drag-handle" title="Drag to move text box (Snaps magnetically to other text)"><i class="fa-solid fa-arrows-up-down-left-right"></i> Move</div>
                <button type="button" class="block-action-btn" data-act="align-left" title="Snap Left with Nearest Document Text (Alt+L)"><i class="fa-solid fa-align-left"></i> Align</button>
                <div class="block-action-sep"></div>
                <button type="button" class="block-action-btn" data-act="bold" title="Toggle Bold (Ctrl+B)"><i class="fa-solid fa-bold"></i></button>
                <button type="button" class="block-action-btn" data-act="italic" title="Toggle Italic (Ctrl+I)"><i class="fa-solid fa-italic"></i></button>
                <button type="button" class="block-action-btn" data-act="underline" title="Toggle Underline (Ctrl+U)"><i class="fa-solid fa-underline"></i></button>
                <div class="block-action-sep"></div>
                <button type="button" class="block-action-btn" data-act="nudge-left" title="Nudge Left (Alt+Left)"><i class="fa-solid fa-caret-left"></i></button>
                <button type="button" class="block-action-btn" data-act="nudge-right" title="Nudge Right (Alt+Right)"><i class="fa-solid fa-caret-right"></i></button>
                <button type="button" class="block-action-btn" data-act="nudge-up" title="Nudge Up (Alt+Up)"><i class="fa-solid fa-caret-up"></i></button>
                <button type="button" class="block-action-btn" data-act="nudge-down" title="Nudge Down (Alt+Down)"><i class="fa-solid fa-caret-down"></i></button>
            `;

            floatingBlockToolbar.addEventListener('mousedown', (e) => {
                const btn = e.target.closest('.block-action-btn');
                if (btn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const act = btn.getAttribute('data-act');
                    if (act === 'align-left') alignLeftWithNearestBlock();
                    else if (act === 'bold') toggleActiveBlockBold();
                    else if (act === 'italic') toggleActiveBlockItalic();
                    else if (act === 'underline') toggleActiveBlockUnderline();
                    else if (act === 'nudge-left') nudgeActiveBlock(-0.2, 0);
                    else if (act === 'nudge-right') nudgeActiveBlock(0.2, 0);
                    else if (act === 'nudge-up') nudgeActiveBlock(0, -0.2);
                    else if (act === 'nudge-down') nudgeActiveBlock(0, 0.2);
                }
            });

            const dragHandle = floatingBlockToolbar.querySelector('.block-drag-handle');
            if (dragHandle) {
                dragHandle.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    startBlockDrag(e);
                });
            }
        }
        return floatingBlockToolbar;
    }

    function updateFloatingToolbarPosition() {
        if (!activeBlockEl || !activeBlockEl.isConnected) {
            if (floatingBlockToolbar && floatingBlockToolbar.parentElement) {
                floatingBlockToolbar.style.display = 'none';
            }
            return;
        }
        const overlay = activeBlockEl.parentElement;
        if (!overlay) return;

        const tb = getOrCreateFloatingToolbar();
        if (tb.parentElement !== overlay) {
            overlay.appendChild(tb);
        }

        const curL = parseFloat(activeBlockEl.style.left) || (activeBlockData ? activeBlockData.left_pct : 0);
        const curT = parseFloat(activeBlockEl.style.top) || (activeBlockData ? activeBlockData.top_pct : 0);

        tb.style.left = `${curL}%`;
        tb.style.top = `calc(${curT}% - 26px)`;
        tb.style.display = 'flex';
    }

    function setActiveBlock(blockDiv, b, p) {
        if (activeBlockEl && activeBlockEl !== blockDiv) {
            activeBlockEl.classList.remove('is-focused', 'is-selected');
        }
        activeBlockEl = blockDiv;
        activeBlockData = b;
        activeBlockPage = p;
        blockDiv.classList.add('is-focused', 'is-selected');
        currentPageIndex = p.page_num;
        updatePageIndicator();

        if (tbFontSelect && b.font_name) {
            ensureFontInSelect(b.font_name);
            tbFontSelect.value = b.font_name;
        }
        if (tbFontSizeSelect && b.font_size_pt) {
            ensureFontSizeInSelect(b.font_size_pt);
            tbFontSizeSelect.value = String(b.font_size_pt);
        }

        updateToolbarEffectStates();
        updateFloatingToolbarPosition();
    }

    function toggleActiveBlockBold() {
        if (!activeBlockEl || !activeBlockData) return;
        activeBlockData.is_bold = !activeBlockData.is_bold;
        activeBlockEl.style.fontWeight = activeBlockData.is_bold ? 'bold' : 'normal';
        activeBlockData.is_modified = true;
        activeBlockEl.classList.add('is-edited');
        updateToolbarEffectStates();
        triggerAutoSave(200);
    }

    function toggleActiveBlockItalic() {
        if (!activeBlockEl || !activeBlockData) return;
        activeBlockData.is_italic = !activeBlockData.is_italic;
        activeBlockEl.style.fontStyle = activeBlockData.is_italic ? 'italic' : 'normal';
        activeBlockData.is_modified = true;
        activeBlockEl.classList.add('is-edited');
        updateToolbarEffectStates();
        triggerAutoSave(200);
    }

    function toggleActiveBlockUnderline() {
        if (!activeBlockEl || !activeBlockData) return;
        activeBlockData.is_underline = !activeBlockData.is_underline;
        activeBlockEl.style.textDecoration = activeBlockData.is_underline ? 'underline' : 'none';
        activeBlockData.is_modified = true;
        activeBlockEl.classList.add('is-edited');
        updateToolbarEffectStates();
        triggerAutoSave(200);
    }

    function updateToolbarEffectStates() {
        if (!activeBlockData) return;
        if (tbBtnBold) tbBtnBold.classList.toggle('active', !!activeBlockData.is_bold);
        if (tbBtnItalic) tbBtnItalic.classList.toggle('active', !!activeBlockData.is_italic);
        if (tbBtnUnderline) tbBtnUnderline.classList.toggle('active', !!activeBlockData.is_underline);

        if (floatingBlockToolbar) {
            const fBold = floatingBlockToolbar.querySelector('[data-act="bold"]');
            const fItalic = floatingBlockToolbar.querySelector('[data-act="italic"]');
            const fUnderline = floatingBlockToolbar.querySelector('[data-act="underline"]');
            if (fBold) fBold.classList.toggle('active', !!activeBlockData.is_bold);
            if (fItalic) fItalic.classList.toggle('active', !!activeBlockData.is_italic);
            if (fUnderline) fUnderline.classList.toggle('active', !!activeBlockData.is_underline);
        }
    }

    function startBlockDrag(e) {
        if (!activeBlockEl || !activeBlockData || !activeBlockPage) return;
        const b = activeBlockData;
        const p = activeBlockPage;
        const sheetCanvas = activeBlockEl.closest('.page-sheet-canvas');
        if (!sheetCanvas) return;

        const guideV = sheetCanvas.querySelector('.docedit-align-guide-v');
        const guideH = sheetCanvas.querySelector('.docedit-align-guide-h');

        const startMouseX = e.clientX;
        const startMouseY = e.clientY;
        const startLeftPct = b.left_pct;
        const startTopPct = b.top_pct;
        const canvasRect = sheetCanvas.getBoundingClientRect();

        activeBlockEl.classList.add('is-moving');

        function onMouseMove(moveEvent) {
            const deltaX = moveEvent.clientX - startMouseX;
            const deltaY = moveEvent.clientY - startMouseY;

            let newLeft = startLeftPct + (deltaX / canvasRect.width) * 100;
            let newTop = startTopPct + (deltaY / canvasRect.height) * 100;

            newLeft = Math.max(0, Math.min(100 - (b.width_pct || 1), newLeft));
            newTop = Math.max(0, Math.min(100 - (b.height_pct || 1), newTop));

            // Magnetic Snapping to other blocks on the same page
            const SNAP_THRESHOLD = 0.8;
            let snapX = null;
            let snapY = null;

            for (const other of p.blocks) {
                if (other.id === b.id) continue;
                if (Math.abs(newLeft - other.left_pct) < SNAP_THRESHOLD) {
                    newLeft = other.left_pct;
                    snapX = newLeft;
                    break;
                }
                const curMid = newLeft + (b.width_pct || 0) / 2;
                const otherMid = other.left_pct + (other.width_pct || 0) / 2;
                if (Math.abs(curMid - otherMid) < SNAP_THRESHOLD) {
                    newLeft = otherMid - (b.width_pct || 0) / 2;
                    snapX = otherMid;
                    break;
                }
            }

            for (const other of p.blocks) {
                if (other.id === b.id) continue;
                if (Math.abs(newTop - other.top_pct) < SNAP_THRESHOLD) {
                    newTop = other.top_pct;
                    snapY = newTop;
                    break;
                }
            }

            if (guideV) {
                if (snapX !== null) {
                    guideV.style.left = `${snapX}%`;
                    guideV.style.display = 'block';
                } else {
                    guideV.style.display = 'none';
                }
            }

            if (guideH) {
                if (snapY !== null) {
                    guideH.style.top = `${snapY}%`;
                    guideH.style.display = 'block';
                } else {
                    guideH.style.display = 'none';
                }
            }

            b.left_pct = Math.round(newLeft * 1000) / 1000;
            b.top_pct = Math.round(newTop * 1000) / 1000;
            activeBlockEl.style.left = `${b.left_pct}%`;
            activeBlockEl.style.top = `${b.top_pct}%`;
            b.is_modified = true;
            activeBlockEl.classList.add('is-edited');

            updateFloatingToolbarPosition();
        }

        function onMouseUp() {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);

            activeBlockEl.classList.remove('is-moving');
            if (guideV) guideV.style.display = 'none';
            if (guideH) guideH.style.display = 'none';

            // Recalculate bbox
            const lx0 = (b.left_pct / 100.0) * p.width;
            const ly0 = (b.top_pct / 100.0) * p.height;
            const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
            const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
            b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];
            triggerAutoSave(200);
        }

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    }

    function alignLeftWithNearestBlock() {
        if (!activeBlockEl || !activeBlockData || !activeBlockPage) return;
        const b = activeBlockData;
        const p = activeBlockPage;

        const otherBlocks = p.blocks.filter(o => o.id !== b.id && Math.abs(o.left_pct - b.left_pct) > 0.05);
        if (otherBlocks.length === 0) return;

        otherBlocks.sort((a, bBlock) => Math.abs(a.left_pct - b.left_pct) - Math.abs(bBlock.left_pct - b.left_pct));
        const target = otherBlocks[0];

        b.left_pct = target.left_pct;
        activeBlockEl.style.left = `${b.left_pct}%`;
        b.is_modified = true;
        activeBlockEl.classList.add('is-edited');

        const lx0 = (b.left_pct / 100.0) * p.width;
        const ly0 = (b.top_pct / 100.0) * p.height;
        const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
        const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
        b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];

        updateFloatingToolbarPosition();

        const sheetCanvas = activeBlockEl.closest('.page-sheet-canvas');
        if (sheetCanvas) {
            const guideV = sheetCanvas.querySelector('.docedit-align-guide-v');
            if (guideV) {
                guideV.style.left = `${b.left_pct}%`;
                guideV.style.display = 'block';
                setTimeout(() => { guideV.style.display = 'none'; }, 1000);
            }
        }
        triggerAutoSave(200);
    }

    function nudgeActiveBlock(dxPct, dyPct) {
        if (!activeBlockEl || !activeBlockData || !activeBlockPage) return;
        const b = activeBlockData;
        const p = activeBlockPage;

        b.left_pct = Math.max(0, Math.min(100 - (b.width_pct || 1), Math.round((b.left_pct + dxPct) * 1000) / 1000));
        b.top_pct = Math.max(0, Math.min(100 - (b.height_pct || 1), Math.round((b.top_pct + dyPct) * 1000) / 1000));

        activeBlockEl.style.left = `${b.left_pct}%`;
        activeBlockEl.style.top = `${b.top_pct}%`;
        b.is_modified = true;
        activeBlockEl.classList.add('is-edited');

        const lx0 = (b.left_pct / 100.0) * p.width;
        const ly0 = (b.top_pct / 100.0) * p.height;
        const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
        const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
        b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];

        updateFloatingToolbarPosition();
        triggerAutoSave(200);
    }

    // Dismiss active block and floating toolbar on outside click
    document.addEventListener('mousedown', (e) => {
        if (e.target.closest('.docedit-text-block') || e.target.closest('.docedit-block-toolbar') || e.target.closest('.tb-btn') || e.target.closest('.tb-select')) {
            return;
        }
        if (activeBlockEl) {
            activeBlockEl.classList.remove('is-focused', 'is-selected');
            activeBlockEl = null;
            activeBlockData = null;
            activeBlockPage = null;
            if (floatingBlockToolbar) {
                floatingBlockToolbar.style.display = 'none';
            }
            if (tbBtnBold) tbBtnBold.classList.remove('active');
            if (tbBtnItalic) tbBtnItalic.classList.remove('active');
            if (tbBtnUnderline) tbBtnUnderline.classList.remove('active');
        }
    });

    function applyZoom() {
        const sheets = document.querySelectorAll('.docedit-page-sheet');
        sheets.forEach(sheet => {
            sheet.style.maxWidth = `${Math.round(820 * (currentZoom / 100))}px`;
        });
        if (tbZoomLevel) tbZoomLevel.textContent = `${currentZoom}%`;
    }

    if (tbPagePrev) {
        tbPagePrev.addEventListener('click', () => {
            if (currentPageIndex > 1) {
                currentPageIndex--;
                const targetSheet = document.getElementById(`doceditPage_${currentPageIndex}`);
                if (targetSheet) targetSheet.scrollIntoView({ behavior: 'smooth', block: 'start' });
                updatePageIndicator();
            }
        });
    }

    if (tbPageNext) {
        tbPageNext.addEventListener('click', () => {
            if (currentPageIndex < currentPagesData.length) {
                currentPageIndex++;
                const targetSheet = document.getElementById(`doceditPage_${currentPageIndex}`);
                if (targetSheet) targetSheet.scrollIntoView({ behavior: 'smooth', block: 'start' });
                updatePageIndicator();
            }
        });
    }

    if (tbZoomIn) {
        tbZoomIn.addEventListener('click', () => {
            currentZoom = Math.min(220, currentZoom + 15);
            applyZoom();
        });
    }

    if (tbZoomOut) {
        tbZoomOut.addEventListener('click', () => {
            currentZoom = Math.max(60, currentZoom - 15);
            applyZoom();
        });
    }

    function attachFuzzyWordTooltips() {
        const fuzzySpans = editorPaper.querySelectorAll('.docedit-fuzzy');
        fuzzySpans.forEach(span => {
            span.addEventListener('click', () => {
                const conf = span.getAttribute('data-conf');
                span.classList.toggle('fuzzy-active');
            });
        });
    }

    function jumpToFuzzyWord(wordText) {
        // First check in layout-preserved blocks
        const blocks = editorPaper.querySelectorAll('.docedit-text-block');
        for (const b of blocks) {
            if (b.textContent.includes(wordText)) {
                b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                b.focus();
                b.classList.add('is-edited');
                return;
            }
        }
        // Fallback for flow mode
        const spans = editorPaper.querySelectorAll('.docedit-fuzzy');
        for (const span of spans) {
            if (span.textContent.trim() === wordText) {
                span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                span.classList.add('fuzzy-active');
                setTimeout(() => span.classList.remove('fuzzy-active'), 2500);
                break;
            }
        }
    }


    function escapeHtml(str) {
        return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // --------------------------------------------------------------------------
    // Editor Toolbar Actions
    // --------------------------------------------------------------------------
    document.querySelectorAll('.tb-btn[data-cmd]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const cmd = btn.getAttribute('data-cmd');
            const val = btn.getAttribute('data-val') || null;

            if (currentMode === 'layout_preserved' && activeBlockEl && activeBlockData) {
                if (cmd === 'bold') {
                    toggleActiveBlockBold();
                    return;
                } else if (cmd === 'italic') {
                    toggleActiveBlockItalic();
                    return;
                } else if (cmd === 'underline') {
                    toggleActiveBlockUnderline();
                    return;
                }
            }

            document.execCommand(cmd, false, val);
            editorPaper.focus();
            triggerAutoSave(200);
        });
    });

    if (tbAlignBlockLeft) {
        tbAlignBlockLeft.addEventListener('click', (e) => {
            e.preventDefault();
            alignLeftWithNearestBlock();
        });
    }
    if (tbNudgeLeft) {
        tbNudgeLeft.addEventListener('click', (e) => {
            e.preventDefault();
            nudgeActiveBlock(-0.2, 0);
        });
    }
    if (tbNudgeRight) {
        tbNudgeRight.addEventListener('click', (e) => {
            e.preventDefault();
            nudgeActiveBlock(0.2, 0);
        });
    }
    if (tbNudgeUp) {
        tbNudgeUp.addEventListener('click', (e) => {
            e.preventDefault();
            nudgeActiveBlock(0, -0.2);
        });
    }
    if (tbNudgeDown) {
        tbNudgeDown.addEventListener('click', (e) => {
            e.preventDefault();
            nudgeActiveBlock(0, 0.2);
        });
    }

    const tbHeadingSelect = document.getElementById('tbHeadingSelect');
    if (tbHeadingSelect) {
        tbHeadingSelect.addEventListener('change', () => {
            const val = tbHeadingSelect.value;
            if (val === 'p') {
                document.execCommand('formatBlock', false, '<p>');
            } else {
                document.execCommand('formatBlock', false, `<${val}>`);
            }
            editorPaper.focus();
        });
    }

    // Font Management Functions
    function ensureFontInSelect(fontName) {
        if (!tbFontSelect || !fontName) return;
        const exists = Array.from(tbFontSelect.options).some(opt => opt.value.toLowerCase() === fontName.toLowerCase());
        if (!exists) {
            let sysGroup = tbFontSelect.querySelector('optgroup[label^="💻 System"]');
            if (!sysGroup) sysGroup = tbFontSelect;
            const opt = document.createElement('option');
            opt.value = fontName;
            opt.textContent = fontName;
            sysGroup.appendChild(opt);
        }
    }

    function ensureFontSizeInSelect(fontSize) {
        if (!tbFontSizeSelect || !fontSize) return;
        const valStr = String(fontSize);
        const exists = Array.from(tbFontSizeSelect.options).some(opt => opt.value === valStr || parseFloat(opt.value) === parseFloat(valStr));
        if (!exists) {
            const opt = document.createElement('option');
            opt.value = valStr;
            opt.textContent = `${fontSize} pt`;
            const options = Array.from(tbFontSizeSelect.options);
            const insertBeforeOpt = options.find(o => parseFloat(o.value) > parseFloat(valStr));
            if (insertBeforeOpt) {
                tbFontSizeSelect.insertBefore(opt, insertBeforeOpt);
            } else {
                tbFontSizeSelect.appendChild(opt);
            }
        }
    }

    function populateFontDropdown(fontData) {
        if (!tbFontSelect || !fontData || !fontData.groups) return;
        const currentVal = tbFontSelect.value;
        tbFontSelect.innerHTML = '';

        const groups = fontData.groups;

        if (groups.recommended && groups.recommended.length > 0) {
            const grp = document.createElement('optgroup');
            grp.label = '✨ Recommended & Classic Book Fonts';
            groups.recommended.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = f.label || f.name;
                grp.appendChild(opt);
            });
            tbFontSelect.appendChild(grp);
        }

        if (groups.project && groups.project.length > 0) {
            const grp = document.createElement('optgroup');
            grp.label = '📁 Project Fonts';
            groups.project.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = `${f.name} (Project Font)`;
                grp.appendChild(opt);
            });
            tbFontSelect.appendChild(grp);
        }

        if (groups.system && groups.system.length > 0) {
            const grp = document.createElement('optgroup');
            grp.label = `💻 System & OS Fonts (${groups.system.length})`;
            groups.system.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = f.name;
                grp.appendChild(opt);
            });
            tbFontSelect.appendChild(grp);
        }

        const preferredVal = currentVal || (currentMeta && currentMeta.font_info ? currentMeta.font_info.name : null);
        if (preferredVal) {
            ensureFontInSelect(preferredVal);
            tbFontSelect.value = preferredVal;
        }
    }

    async function refreshFontList(force = false) {
        if (!tbFontSelect) return;
        if (tbFontRefresh) tbFontRefresh.classList.add('spinning');
        try {
            const url = force ? '/docedit/api/fonts/?refresh=1' : '/docedit/api/fonts/';
            const resp = await fetch(url);
            const data = await resp.json();
            if (data.success) {
                populateFontDropdown(data);
                if (force) {
                    showNotice('System Fonts Refreshed', `Scanned system & OS: ${data.total_count} fonts available.`);
                }
            }
        } catch (err) {
            console.error('Failed fetching font list:', err);
        } finally {
            if (tbFontRefresh) {
                setTimeout(() => tbFontRefresh.classList.remove('spinning'), 400);
            }
        }
    }

    // Refresh OS Fonts Button
    if (tbFontRefresh) {
        tbFontRefresh.addEventListener('click', () => {
            refreshFontList(true);
        });
    }

    // Install Font Modal Handlers
    function showInstallFontModal() {
        if (!installFontModal) return;
        selectedFontFile = null;
        if (selectedFontFileName) {
            selectedFontFileName.style.display = 'none';
            selectedFontFileName.textContent = '';
        }
        if (fontFileInput) fontFileInput.value = '';
        if (fontSearchInput) fontSearchInput.value = '';
        if (fontInstallStatus) {
            fontInstallStatus.style.display = 'none';
            fontInstallStatus.className = 'font-install-status';
            fontInstallStatus.textContent = '';
        }
        installFontModal.classList.add('show');
    }

    function hideInstallFontModal() {
        if (installFontModal) installFontModal.classList.remove('show');
    }

    if (tbInstallFontBtn) {
        tbInstallFontBtn.addEventListener('click', showInstallFontModal);
    }

    if (modalBtnCloseFontInstall) {
        modalBtnCloseFontInstall.addEventListener('click', hideInstallFontModal);
    }

    if (installFontModal) {
        installFontModal.addEventListener('click', (e) => {
            if (e.target === installFontModal) hideInstallFontModal();
        });
    }

    // Install Modal Tabs
    if (tabBtnFontFile && tabBtnFontOnline) {
        tabBtnFontFile.addEventListener('click', () => {
            activeInstallTab = 'file';
            tabBtnFontFile.classList.add('active');
            tabBtnFontOnline.classList.remove('active');
            if (tabContentFontFile) tabContentFontFile.classList.add('active');
            if (tabContentFontOnline) tabContentFontOnline.classList.remove('active');
        });

        tabBtnFontOnline.addEventListener('click', () => {
            activeInstallTab = 'online';
            tabBtnFontOnline.classList.add('active');
            tabBtnFontFile.classList.remove('active');
            if (tabContentFontOnline) tabContentFontOnline.classList.add('active');
            if (tabContentFontFile) tabContentFontFile.classList.remove('active');
        });
    }

    // Dropzone for Font Files
    if (fontFileDropzone && fontFileInput) {
        fontFileDropzone.addEventListener('click', () => {
            fontFileInput.click();
        });

        fontFileDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            fontFileDropzone.classList.add('drag-over');
        });

        fontFileDropzone.addEventListener('dragleave', () => {
            fontFileDropzone.classList.remove('drag-over');
        });

        fontFileDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            fontFileDropzone.classList.remove('drag-over');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleSelectedFontFile(e.dataTransfer.files[0]);
            }
        });

        fontFileInput.addEventListener('change', () => {
            if (fontFileInput.files && fontFileInput.files.length > 0) {
                handleSelectedFontFile(fontFileInput.files[0]);
            }
        });
    }

    function handleSelectedFontFile(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext !== 'ttf' && ext !== 'otf') {
            if (fontInstallStatus) {
                fontInstallStatus.className = 'font-install-status error';
                fontInstallStatus.style.display = 'block';
                fontInstallStatus.textContent = 'Please choose a TrueType (.ttf) or OpenType (.otf) font file.';
            }
            return;
        }
        selectedFontFile = file;
        if (selectedFontFileName) {
            selectedFontFileName.style.display = 'inline-block';
            selectedFontFileName.textContent = `Selected: ${file.name} (${formatBytes(file.size)})`;
        }
        if (fontInstallStatus) fontInstallStatus.style.display = 'none';
    }

    // Submit Font Installation
    if (modalBtnSubmitFontInstall) {
        modalBtnSubmitFontInstall.addEventListener('click', async () => {
            if (activeInstallTab === 'file') {
                if (!selectedFontFile) {
                    if (fontInstallStatus) {
                        fontInstallStatus.className = 'font-install-status error';
                        fontInstallStatus.style.display = 'block';
                        fontInstallStatus.textContent = 'Please select a .ttf or .otf font file to install.';
                    }
                    return;
                }

                const formData = new FormData();
                formData.append('font_file', selectedFontFile);

                modalBtnSubmitFontInstall.disabled = true;
                modalBtnSubmitFontInstall.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Installing...';
                if (fontInstallStatus) {
                    fontInstallStatus.className = 'font-install-status info';
                    fontInstallStatus.style.display = 'block';
                    fontInstallStatus.textContent = 'Installing font into Windows system registry...';
                }

                try {
                    const resp = await fetch('/docedit/api/fonts/install/', {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: formData,
                    });
                    const resData = await resp.json();
                    if (resData.success) {
                        if (resData.fonts) populateFontDropdown(resData.fonts);
                        ensureFontInSelect(resData.name);
                        tbFontSelect.value = resData.name;
                        editorPaper.style.fontFamily = `"${resData.name}", serif`;
                        panFontName.textContent = resData.name;
                        showNotice('Font Installed', resData.message || `Font '${resData.name}' installed to system successfully.`);
                        hideInstallFontModal();

                        if (currentSessionId) {
                            fetch(`/docedit/api/font/${currentSessionId}/`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                                body: JSON.stringify({ font_name: resData.name }),
                            }).catch(() => {});
                        }
                    } else {
                        if (fontInstallStatus) {
                            fontInstallStatus.className = 'font-install-status error';
                            fontInstallStatus.style.display = 'block';
                            fontInstallStatus.textContent = resData.error || 'Failed installing font.';
                        }
                    }
                } catch (err) {
                    if (fontInstallStatus) {
                        fontInstallStatus.className = 'font-install-status error';
                        fontInstallStatus.style.display = 'block';
                        fontInstallStatus.textContent = 'Network or server error installing font.';
                    }
                } finally {
                    modalBtnSubmitFontInstall.disabled = false;
                    modalBtnSubmitFontInstall.innerHTML = '<i class="fa-solid fa-download"></i> Install to System';
                }
            } else {
                // Online search tab
                const name = fontSearchInput ? fontSearchInput.value.trim() : '';
                if (!name) {
                    if (fontInstallStatus) {
                        fontInstallStatus.className = 'font-install-status error';
                        fontInstallStatus.style.display = 'block';
                        fontInstallStatus.textContent = 'Please enter a font family name.';
                    }
                    return;
                }

                modalBtnSubmitFontInstall.disabled = true;
                modalBtnSubmitFontInstall.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Downloading & Installing...';
                if (fontInstallStatus) {
                    fontInstallStatus.className = 'font-install-status info';
                    fontInstallStatus.style.display = 'block';
                    fontInstallStatus.textContent = `Downloading '${name}' and registering into Windows system...`;
                }

                try {
                    const resp = await fetch('/docedit/api/fonts/install/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: JSON.stringify({ font_name: name }),
                    });
                    const resData = await resp.json();
                    if (resData.success) {
                        if (resData.fonts) populateFontDropdown(resData.fonts);
                        ensureFontInSelect(resData.name);
                        tbFontSelect.value = resData.name;
                        editorPaper.style.fontFamily = `"${resData.name}", serif`;
                        panFontName.textContent = resData.name;
                        showNotice('Font Installed', resData.message || `Font '${resData.name}' installed to system successfully.`);
                        hideInstallFontModal();

                        if (currentSessionId) {
                            fetch(`/docedit/api/font/${currentSessionId}/`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                                body: JSON.stringify({ font_name: resData.name }),
                            }).catch(() => {});
                        }
                    } else {
                        if (fontInstallStatus) {
                            fontInstallStatus.className = 'font-install-status error';
                            fontInstallStatus.style.display = 'block';
                            fontInstallStatus.textContent = resData.error || 'Failed downloading/installing font.';
                        }
                    }
                } catch (err) {
                    if (fontInstallStatus) {
                        fontInstallStatus.className = 'font-install-status error';
                        fontInstallStatus.style.display = 'block';
                        fontInstallStatus.textContent = 'Network or server error.';
                    }
                } finally {
                    modalBtnSubmitFontInstall.disabled = false;
                    modalBtnSubmitFontInstall.innerHTML = '<i class="fa-solid fa-download"></i> Install to System';
                }
            }
        });
    }

    // Font Switching via Toolbar
    if (tbFontSelect) {
        tbFontSelect.addEventListener('change', async () => {
            const newFont = tbFontSelect.value;
            editorPaper.style.fontFamily = `"${newFont}", serif`;
            panFontName.textContent = newFont;

            // In layout_preserved mode: if a specific block is active, update that block; otherwise update all
            if (currentMode === 'layout_preserved') {
                if (activeBlockEl && activeBlockData) {
                    activeBlockEl.style.fontFamily = `"${newFont}", serif`;
                    activeBlockData.font_name = newFont;
                    activeBlockData.is_modified = true;
                    activeBlockEl.classList.add('is-edited');
                } else {
                    const blocks = editorPaper.querySelectorAll('.docedit-text-block');
                    blocks.forEach(b => {
                        b.style.fontFamily = `"${newFont}", serif`;
                        b.classList.add('is-edited');
                    });
                    if (currentPagesData && currentPagesData.length > 0) {
                        currentPagesData.forEach(p => {
                            if (p.blocks) {
                                p.blocks.forEach(b => {
                                    b.font_name = newFont;
                                    b.is_modified = true;
                                });
                            }
                        });
                    }
                }
            }
            triggerAutoSave(100);

            if (currentSessionId) {
                try {
                    const curSize = tbFontSizeSelect ? parseFloat(tbFontSizeSelect.value) : null;
                    const resp = await fetch(`/docedit/api/font/${currentSessionId}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: JSON.stringify({ font_name: newFont, size_pt: curSize }),
                    });
                    const resData = await resp.json();
                    if (resData.success) {
                        updatePanFromStatus({ ...currentMeta, font_info: resData.font_info, editor_font_css: resData.editor_font_css });
                    }
                } catch (err) {
                    console.error('Font change error:', err);
                }
            }
        });
    }

    // Background sync of system fonts on page load
    setTimeout(() => { refreshFontList(false); }, 1000);

    // Font Size Adjuster via Toolbar
    if (tbFontSizeSelect) {
        tbFontSizeSelect.addEventListener('change', () => {
            const newSize = tbFontSizeSelect.value;
            const newSizeNum = parseFloat(newSize);
            editorPaper.style.fontSize = `${newSize}pt`;
            panFontSize.textContent = `${newSize} pt`;

            // In layout_preserved mode: if a specific block is active, update that block; otherwise update all
            if (currentMode === 'layout_preserved') {
                if (activeBlockEl && activeBlockData) {
                    activeBlockEl.style.fontSize = `${newSize}pt`;
                    activeBlockData.font_size_pt = newSizeNum;
                    activeBlockData.is_modified = true;
                    activeBlockEl.classList.add('is-edited');
                } else {
                    const blocks = editorPaper.querySelectorAll('.docedit-text-block');
                    blocks.forEach(b => {
                        b.style.fontSize = `${newSize}pt`;
                        b.classList.add('is-edited');
                    });
                    if (currentPagesData && currentPagesData.length > 0) {
                        currentPagesData.forEach(p => {
                            if (p.blocks) {
                                p.blocks.forEach(b => {
                                    b.font_size_pt = newSizeNum;
                                    b.is_modified = true;
                                });
                            }
                        });
                    }
                }
            }
            triggerAutoSave(100);

            if (currentSessionId) {
                const curFont = tbFontSelect ? tbFontSelect.value : (currentMeta?.font_info?.name || 'EB Garamond');
                fetch(`/docedit/api/font/${currentSessionId}/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify({ font_name: curFont, size_pt: newSizeNum }),
                }).catch(() => {});
            }
        });
    }

    // Toggle Fuzzy Highlighting
    if (tbFuzzyToggle) {
        tbFuzzyToggle.addEventListener('click', () => {
            showFuzzyHighlights = !showFuzzyHighlights;
            if (showFuzzyHighlights) {
                document.body.classList.remove('hide-fuzzy');
                tbFuzzyToggle.innerHTML = '<i class="fa-solid fa-highlighter"></i> Fuzzy Highlights: ON';
            } else {
                document.body.classList.add('hide-fuzzy');
                tbFuzzyToggle.innerHTML = '<i class="fa-regular fa-eye-slash"></i> Fuzzy Highlights: OFF';
            }
        });
    }

    // --------------------------------------------------------------------------
    // Table & Divider Line Insertion Tools
    // --------------------------------------------------------------------------
    if (tbInsertTable) {
        tbInsertTable.addEventListener('click', () => {
            const tableHtml = `
                <table class="docedit-table" style="border-collapse: collapse; width: 100%; margin: 1.2rem 0; border: 1px solid #777;">
                    <thead>
                        <tr>
                            <th style="border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);">Column 1</th>
                            <th style="border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);">Column 2</th>
                            <th style="border: 1px solid #777; padding: 6px 10px; font-weight: bold; background: rgba(128,128,128,0.12);">Column 3</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Item 1</td>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Details</td>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Reference</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Item 2</td>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Details</td>
                            <td style="border: 1px solid #777; padding: 6px 10px;">Reference</td>
                        </tr>
                    </tbody>
                </table>
                <p><br></p>
            `;
            editorPaper.focus();
            document.execCommand('insertHTML', false, tableHtml);
            triggerAutoSave(200);
        });
    }

    if (tbAddRow) {
        tbAddRow.addEventListener('click', () => {
            const sel = window.getSelection();
            let table = null;
            if (sel && sel.rangeCount > 0) {
                let node = sel.anchorNode;
                while (node && node !== editorPaper) {
                    if (node.nodeName === 'TABLE') {
                        table = node;
                        break;
                    }
                    node = node.parentNode;
                }
            }
            if (!table) {
                // If not directly selected, find last table in editor
                table = editorPaper.querySelector('table');
            }

            if (table) {
                const colCount = table.rows[0] ? table.rows[0].cells.length : 3;
                const tbody = table.querySelector('tbody') || table;
                const newRow = document.createElement('tr');
                for (let i = 0; i < colCount; i++) {
                    const newCell = document.createElement('td');
                    newCell.style.border = '1px solid #777';
                    newCell.style.padding = '6px 10px';
                    newCell.textContent = 'New cell';
                    newRow.appendChild(newCell);
                }
                tbody.appendChild(newRow);
                triggerAutoSave(200);
            } else {
                alert('Please place your cursor inside a table or click Table button first.');
            }
        });
    }

    if (tbInsertLine) {
        tbInsertLine.addEventListener('click', () => {
            editorPaper.focus();
            document.execCommand('insertHTML', false, '<hr class="docedit-line" style="border: none; border-top: 1px solid #777; margin: 1.5rem 0;" /><p><br></p>');
            triggerAutoSave(200);
        });
    }

    if (editorPaper) {
        editorPaper.addEventListener('input', () => {
            triggerAutoSave(700);
        });
    }

    // --------------------------------------------------------------------------
    // Format Selection Synchronization
    // --------------------------------------------------------------------------
    if (panDownloadFormat && modalDownloadFormat) {
        panDownloadFormat.addEventListener('change', () => {
            modalDownloadFormat.value = panDownloadFormat.value;
        });
        modalDownloadFormat.addEventListener('change', () => {
            panDownloadFormat.value = modalDownloadFormat.value;
        });
    }

    // --------------------------------------------------------------------------
    // Save & Download Flow (with confirmation dialog & note that file is not saved)
    // --------------------------------------------------------------------------
    if (panBtnDownload) {
        panBtnDownload.addEventListener('click', () => {
            if (!currentSessionId) return;
            // Ask user to save/confirm before download
            confirmModal.classList.add('show');
        });
    }

    if (modalBtnKeepEditing) {
        modalBtnKeepEditing.addEventListener('click', () => {
            confirmModal.classList.remove('show');
            editorPaper.focus();
        });
    }

    if (confirmModal) {
        confirmModal.addEventListener('click', (e) => {
            if (e.target === confirmModal) {
                confirmModal.classList.remove('show');
            }
        });
    }

    if (modalBtnConfirm) {
        modalBtnConfirm.addEventListener('click', async () => {
            confirmModal.classList.remove('show');
            await executeSaveAndDownload();
        });
    }

    async function executeSaveAndDownload() {
        if (!currentSessionId) return;
        if (autoSaveTimeout) {
            clearTimeout(autoSaveTimeout);
            autoSaveTimeout = null;
        }
        syncBlocksFromDom();
        panBtnDownload.disabled = true;
        panBtnDownload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving & Preparing Download...';

        try {
            const htmlContent = editorPaper.innerHTML;
            const fontName = tbFontSelect ? tbFontSelect.value : (panFontName.textContent || 'EB Garamond');
            const fontSize = tbFontSizeSelect ? tbFontSizeSelect.value : 12;
            const chosenFormat = (panDownloadFormat ? panDownloadFormat.value : 'pdf') || 'pdf';

            let payload = {
                font_name: fontName,
                font_size_pt: fontSize,
                export_format: chosenFormat,
            };

            if (currentMode === 'layout_preserved' && currentPagesData.length > 0) {
                currentPagesData.forEach(p => {
                    p.blocks.forEach(b => {
                        const el = document.querySelector(`.docedit-text-block[data-block-id="${b.id}"]`);
                        if (el) {
                            const newText = el.innerText.trim();
                            if (newText !== b.text) {
                                b.text = newText;
                                b.is_modified = true;
                            }
                            const curL = parseFloat(el.style.left);
                            const curT = parseFloat(el.style.top);
                            if (!isNaN(curL) && Math.abs(curL - b.left_pct) > 0.001) {
                                b.left_pct = Math.round(curL * 1000) / 1000;
                                b.is_modified = true;
                            }
                            if (!isNaN(curT) && Math.abs(curT - b.top_pct) > 0.001) {
                                b.top_pct = Math.round(curT * 1000) / 1000;
                                b.is_modified = true;
                            }
                            if (el.style.fontWeight === 'bold' || parseInt(el.style.fontWeight, 10) >= 600) {
                                b.is_bold = true;
                            } else if (el.style.fontWeight === 'normal') {
                                b.is_bold = false;
                            }
                            if (el.style.fontStyle === 'italic') {
                                b.is_italic = true;
                            } else if (el.style.fontStyle === 'normal') {
                                b.is_italic = false;
                            }
                            if (el.style.textDecoration && el.style.textDecoration.includes('underline')) {
                                b.is_underline = true;
                            } else if (el.style.textDecoration === 'none') {
                                b.is_underline = false;
                            }
                        }

                        // Recalculate bbox from current left_pct, top_pct, width_pct, height_pct
                        const lx0 = (b.left_pct / 100.0) * p.width;
                        const ly0 = (b.top_pct / 100.0) * p.height;
                        const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
                        const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
                        b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];
                    });
                });
                payload.pages_data = currentPagesData;
                payload.html_content = editorPaper.innerHTML;
            } else {
                payload.html_content = htmlContent;
            }

            const resp = await fetch(`/docedit/api/save/${currentSessionId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(payload),
            });

            const data = await resp.json();
            if (!data.success) {
                alert('Save failed: ' + (data.error || 'Could not save document.'));
                panBtnDownload.disabled = false;
                panBtnDownload.innerHTML = '<i class="fa-solid fa-file-arrow-down"></i> Save & Download Document';
                return;
            }

            // Trigger browser download to user's desired local folder
            const downloadLink = document.createElement('a');
            downloadLink.href = data.download_url;
            downloadLink.download = data.download_filename || 'edited_document';
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);

            // Store notification flag in sessionStorage before navigating to /docedit/
            try {
                sessionStorage.setItem('docedit_download_success', '1');
            } catch (e) {
                console.warn('Could not set sessionStorage item:', e);
            }

            // REQUIRED NOTICE: Display success message with note that file has not been saved on server
            showNotice(
                'Document downloaded successfully to your system!',
                'Note: This file has not been permanently saved on the server. Please keep your downloaded copy in your desired folder.'
            );

            panBtnDownload.disabled = false;
            panBtnDownload.innerHTML = '<i class="fa-solid fa-check"></i> Downloaded! Redirecting...';

            // Bring user back to /docedit/
            setTimeout(() => {
                window.location.href = '/docedit/';
            }, 800);
        } catch (err) {
            console.error('Save & Download error:', err);
            alert('Failed to save & download: ' + err.message);
            panBtnDownload.disabled = false;
            panBtnDownload.innerHTML = '<i class="fa-solid fa-file-arrow-down"></i> Save & Download Document';
        }
    }

    // --------------------------------------------------------------------------
    // Cancel & Reset Flow
    // --------------------------------------------------------------------------
    if (panBtnCancel) {
        panBtnCancel.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to cancel? All temporary document data will be cleared.')) {
                return;
            }
            if (currentSessionId) {
                try {
                    await fetch(`/docedit/api/cancel/${currentSessionId}/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                        },
                    });
                } catch (err) {
                    console.error('Cancel error:', err);
                }
            }
            resetWorkspace();
        });
    }

    function resetWorkspace() {
        if (pollInterval) clearInterval(pollInterval);
        currentSessionId = null;
        currentMeta = null;
        currentMode = 'flow';
        currentPagesData = [];
        currentPageIndex = 1;
        currentZoom = 100;
        if (tbPageNavGroup) tbPageNavGroup.style.display = 'none';
        if (tbPageSep) tbPageSep.style.display = 'none';
        if (fileInput) fileInput.value = '';
        editorPaper.contentEditable = "true";
        editorPaper.innerHTML = '<p></p>';
        workspace.classList.remove('active');
        dropzone.style.display = 'block';
        hideNotice();
    }
});

