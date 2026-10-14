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
    const tbFontSizeSelect = document.getElementById('tbFontSizeSelect');
    const tbFuzzyToggle = document.getElementById('tbFuzzyToggle');

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

    // State
    let currentSessionId = null;
    let pollInterval = null;
    let currentMeta = null;
    let showFuzzyHighlights = true;
    let currentMode = 'flow'; // 'flow' or 'layout_preserved'
    let currentPagesData = [];
    let currentPageIndex = 1;
    let currentZoom = 100;


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
            if (tbFontSelect) tbFontSelect.value = font.name;
        }
        if (font.size_pt) {
            panFontSize.textContent = `${font.size_pt} pt`;
            if (tbFontSizeSelect) tbFontSizeSelect.value = String(font.size_pt);
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
        editorPaper.style.fontFamily = `"${fontName}", serif`;
        editorPaper.style.fontSize = `${fontSize}pt`;

        if (data.is_layout_preserved && data.pages && data.pages.length > 0) {
            currentMode = 'layout_preserved';
            currentPagesData = data.pages;
            editorPaper.contentEditable = "false";
            if (tbPageNavGroup) tbPageNavGroup.style.display = 'inline-flex';
            if (tbPageSep) tbPageSep.style.display = 'inline-block';
            currentPageIndex = 1;
            updatePageIndicator();
            renderLayoutPreservedPages(data.pages, fontName, fontSize);
        } else {
            currentMode = 'flow';
            currentPagesData = [];
            editorPaper.contentEditable = "true";
            if (tbPageNavGroup) tbPageNavGroup.style.display = 'none';
            if (tbPageSep) tbPageSep.style.display = 'none';
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
                blockDiv.textContent = b.text;

                blockDiv.addEventListener('focus', () => {
                    blockDiv.classList.add('is-focused');
                    currentPageIndex = p.page_num;
                    updatePageIndicator();
                });

                blockDiv.addEventListener('input', () => {
                    b.text = blockDiv.innerText.trim();
                    b.is_modified = true;
                    blockDiv.classList.add('is-edited');
                });

                blockDiv.addEventListener('blur', () => {
                    blockDiv.classList.remove('is-focused');
                    if (b.is_modified) {
                        blockDiv.classList.add('is-edited');
                    }
                });

                overlay.appendChild(blockDiv);
            });

            canvas.appendChild(bgImg);
            canvas.appendChild(overlay);
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
            document.execCommand(cmd, false, val);
            editorPaper.focus();
        });
    });

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

    // Font Switching via Toolbar
    if (tbFontSelect) {
        tbFontSelect.addEventListener('change', async () => {
            const newFont = tbFontSelect.value;
            editorPaper.style.fontFamily = `"${newFont}", serif`;
            panFontName.textContent = newFont;

            if (currentSessionId) {
                try {
                    const resp = await fetch(`/docedit/api/font/${currentSessionId}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: JSON.stringify({ font_name: newFont }),
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

    // Font Size Adjuster via Toolbar
    if (tbFontSizeSelect) {
        tbFontSizeSelect.addEventListener('change', () => {
            const newSize = tbFontSizeSelect.value;
            editorPaper.style.fontSize = `${newSize}pt`;
            panFontSize.textContent = `${newSize} pt`;
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
            } else {
                alert('Please place your cursor inside a table or click Table button first.');
            }
        });
    }

    if (tbInsertLine) {
        tbInsertLine.addEventListener('click', () => {
            editorPaper.focus();
            document.execCommand('insertHTML', false, '<hr class="docedit-line" style="border: none; border-top: 1px solid #777; margin: 1.5rem 0;" /><p><br></p>');
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

    if (modalBtnConfirm) {
        modalBtnConfirm.addEventListener('click', async () => {
            confirmModal.classList.remove('show');
            await executeSaveAndDownload();
        });
    }

    async function executeSaveAndDownload() {
        if (!currentSessionId) return;
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
                        }
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

            // REQUIRED NOTICE: Display success message with note that file has not been saved on server
            showNotice(
                'Document downloaded successfully to your system!',
                'Note: This file has not been permanently saved on the server. Please keep your downloaded copy in your desired folder.'
            );

            panBtnDownload.disabled = false;
            panBtnDownload.innerHTML = '<i class="fa-solid fa-check"></i> Downloaded';
            setTimeout(() => {
                panBtnDownload.innerHTML = '<i class="fa-solid fa-file-arrow-down"></i> Save & Download Document';
            }, 3000);
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

