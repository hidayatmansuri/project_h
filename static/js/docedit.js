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
    const panFontMetricAlert = document.getElementById('panFontMetricAlert');
    const panFontMetricText = document.getElementById('panFontMetricText');
    const panFontResRow = document.getElementById('panFontResRow');
    const panFontMatchVal = document.getElementById('panFontMatchVal');
    const panFuzzyCount = document.getElementById('panFuzzyCount');
    const panFuzzyList = document.getElementById('panFuzzyList');
    const panBtnSave = document.getElementById('panBtnSave');
    const panBtnDownload = document.getElementById('panBtnDownload');
    const panBtnCancel = document.getElementById('panBtnCancel');

    // Toolbar Elements
    const tbBtnSave = document.getElementById('tbBtnSave');
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
    const tbZoomFitWidth = document.getElementById('tbZoomFitWidth');
    const tbZoomFitPage = document.getElementById('tbZoomFitPage');

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

    // Phase 7 Toolbar & Action Elements
    const tbBtnThumbnails = document.getElementById('tbBtnThumbnails');
    const tbBtnUndo = document.getElementById('tbBtnUndo');
    const tbBtnRedo = document.getElementById('tbBtnRedo');
    const tbBtnFindReplace = document.getElementById('tbBtnFindReplace');
    const tbBtnBeforeAfter = document.getElementById('tbBtnBeforeAfter');
    const tbBtnAddBox = document.getElementById('tbBtnAddBox');
    const tbBtnDeleteBox = document.getElementById('tbBtnDeleteBox');
    const tbBtnApplyAll = document.getElementById('tbBtnApplyAll');

    // Phase 7 Thumbnails Sidebar Elements
    const doceditThumbnailsSidebar = document.getElementById('doceditThumbnailsSidebar');
    const thumbBtnCollapse = document.getElementById('thumbBtnCollapse');
    const thumbList = document.getElementById('thumbList');
    const thumbPageCount = document.getElementById('thumbPageCount');

    // Phase 7 Compare / Before Banner
    const doceditBeforeBanner = document.getElementById('doceditBeforeBanner');

    // Phase 7 Find & Replace Elements
    const doceditFindReplacePanel = document.getElementById('doceditFindReplacePanel');
    const frSearchInput = document.getElementById('frSearchInput');
    const frReplaceInput = document.getElementById('frReplaceInput');
    const frMatchCount = document.getElementById('frMatchCount');
    const frBtnPrev = document.getElementById('frBtnPrev');
    const frBtnNext = document.getElementById('frBtnNext');
    const frBtnReplace = document.getElementById('frBtnReplace');
    const frBtnReplaceAll = document.getElementById('frBtnReplaceAll');
    const frMatchCase = document.getElementById('frMatchCase');
    const frWholeWord = document.getElementById('frWholeWord');
    const frPageOnly = document.getElementById('frPageOnly');
    const frBtnClose = document.getElementById('frBtnClose');
    const frResultsList = document.getElementById('frResultsList');

    // Phase 7 Apply to All Modal Elements
    const doceditApplyAllModal = document.getElementById('doceditApplyAllModal');
    const applySourceFont = document.getElementById('applySourceFont');
    const applySourceSize = document.getElementById('applySourceSize');
    const applySourceColor = document.getElementById('applySourceColor');
    const applyOptFont = document.getElementById('applyOptFont');
    const applyOptSize = document.getElementById('applyOptSize');
    const applyOptColor = document.getElementById('applyOptColor');
    const applyMatchCount = document.getElementById('applyMatchCount');
    const modalBtnCloseApplyAll = document.getElementById('modalBtnCloseApplyAll');
    const modalBtnConfirmApplyAll = document.getElementById('modalBtnConfirmApplyAll');

    // Phase 7 Issues / Overflow Elements
    const panIssuesCard = document.getElementById('panIssuesCard');
    const panIssuesCount = document.getElementById('panIssuesCount');
    const panIssuesList = document.getElementById('panIssuesList');

    // State
    let currentSessionId = null;
    let pollInterval = null;
    let currentMeta = null;
    let showFuzzyHighlights = true;
    let currentMode = 'flow'; // 'flow' or 'layout_preserved'
    let currentPagesData = [];
    let currentPageIndex = 1;
    let currentZoom = 100;

    // Phase 7 Interactive State
    let isAddingBoxMode = false;
    let isBeforeModeActive = false;
    let isHoldingBKey = false;
    let findMatches = [];
    let currentMatchIndex = -1;

    // Active block tracking for layout-preserved mode
    let activeBlockEl = null;
    let activeBlockData = null;
    let activeBlockPage = null;
    let floatingBlockToolbar = null;

    // Phase 8 Confidence Heatmap & Review Queue Elements
    const tbBtnHeatmap = document.getElementById('tbBtnHeatmap');
    const tbHeatmapControls = document.getElementById('tbHeatmapControls');
    const tbHeatmapSlider = document.getElementById('tbHeatmapSlider');
    const tbHeatmapValue = document.getElementById('tbHeatmapValue');
    const tbBtnReviewQueue = document.getElementById('tbBtnReviewQueue');
    const tbReviewQueueCount = document.getElementById('tbReviewQueueCount');
    const panBtnOpenReviewQueue = document.getElementById('panBtnOpenReviewQueue');
    const doceditReviewQueuePanel = document.getElementById('doceditReviewQueuePanel');
    const rqBtnClose = document.getElementById('rqBtnClose');
    const rqProgressBadge = document.getElementById('rqProgressBadge');
    const rqProgressBarFill = document.getElementById('rqProgressBarFill');
    const rqActiveCard = document.getElementById('rqActiveCard');
    const rqWordIndex = document.getElementById('rqWordIndex');
    const rqWordConfidence = document.getElementById('rqWordConfidence');
    const rqFuzzyReasons = document.getElementById('rqFuzzyReasons');
    const rqCropImg = document.getElementById('rqCropImg');
    const rqCropFallback = document.getElementById('rqCropFallback');
    const rqWordInput = document.getElementById('rqWordInput');
    const rqBtnAccept = document.getElementById('rqBtnAccept');
    const rqBtnEdit = document.getElementById('rqBtnEdit');
    const rqBtnSkip = document.getElementById('rqBtnSkip');
    const rqCompletedState = document.getElementById('rqCompletedState');
    const rqBtnRestart = document.getElementById('rqBtnRestart');
    const rqWordsList = document.getElementById('rqWordsList');
    const rqListRemaining = document.getElementById('rqListRemaining');

    // Phase 8 State
    let isHeatmapActive = false;
    let heatmapThreshold = 70;
    let reviewWordsList = [];
    let reviewCurrentIndex = -1;
    let isReviewQueueOpen = false;


    // Helper: Escapes HTML text to prevent XSS
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Helper: Client-side HTML sanitization allowlist (DOMParser-based)
    // Never assign unsanitised server HTML to innerHTML.
    function sanitizeHtml(rawHtml) {
        if (!rawHtml || typeof rawHtml !== 'string') return '';
        const parser = new DOMParser();
        const doc = parser.parseFromString(rawHtml, 'text/html');

        const ALLOWED_TAGS = new Set([
            'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
            'strong', 'b', 'em', 'i', 'u', 's', 'span', 'br', 'hr',
            'ul', 'ol', 'li', 'div', 'img'
        ]);

        const DROP_TAGS = new Set([
            'script', 'style', 'iframe', 'object', 'embed', 'applet', 'svg', 'math', 'noscript'
        ]);

        const ALLOWED_ATTRS = new Set([
            'class', 'style', 'id', 'data-block-id', 'data-page', 'data-font-size-pt',
            'data-rotation', 'contenteditable', 'spellcheck', 'colspan', 'rowspan',
            'src', 'alt', 'draggable', 'border', 'cellpadding', 'cellspacing', 'scope',
            'data-word-id', 'data-conf', 'data-conf-tier', 'data-fuzzy-word', 'title'
        ]);

        function cleanNode(node) {
            const children = Array.from(node.childNodes);
            for (const child of children) {
                if (child.nodeType === Node.ELEMENT_NODE) {
                    const tag = child.tagName.toLowerCase();
                    if (DROP_TAGS.has(tag)) {
                        child.remove();
                        continue;
                    }
                    if (!ALLOWED_TAGS.has(tag)) {
                        cleanNode(child);
                        while (child.firstChild) {
                            child.parentNode.insertBefore(child.firstChild, child);
                        }
                        child.remove();
                        continue;
                    }
                    const attrs = Array.from(child.attributes);
                    for (const attr of attrs) {
                        const attrName = attr.name.toLowerCase();
                        if (attrName.startsWith('on') || !ALLOWED_ATTRS.has(attrName)) {
                            child.removeAttribute(attr.name);
                            continue;
                        }
                        if (attrName === 'style') {
                            const val = attr.value;
                            if (/javascript:|expression\(|behavior:|-moz-binding|@import|url\(/i.test(val)) {
                                child.removeAttribute('style');
                            }
                        } else if (attrName === 'src') {
                            const val = attr.value.trim();
                            if (!val.startsWith('/') && !val.startsWith('data:image/') && !val.startsWith('http://') && !val.startsWith('https://')) {
                                child.removeAttribute('src');
                            }
                        }
                    }
                    cleanNode(child);
                }
            }
        }

        cleanNode(doc.body);
        return doc.body.innerHTML;
    }

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
    let docVersion = 0;

    function setAutoSaveStatus(status, detailText) {
        if (tbAutoSaveIndicator) {
            if (status === 'saving') {
                tbAutoSaveIndicator.style.background = 'rgba(234, 179, 8, 0.15)';
                tbAutoSaveIndicator.style.color = '#ca8a04';
                tbAutoSaveIndicator.style.cursor = 'default';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-arrows-rotate fa-spin';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Saving...';
            } else if (status === 'saved') {
                tbAutoSaveIndicator.style.background = 'rgba(16, 185, 129, 0.12)';
                tbAutoSaveIndicator.style.color = '#059669';
                tbAutoSaveIndicator.style.cursor = 'default';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-cloud-arrow-up';
                const text = detailText || 'Saved';
                if (tbAutoSaveText) tbAutoSaveText.textContent = text;
            } else if (status === 'modified') {
                tbAutoSaveIndicator.style.background = 'rgba(59, 130, 246, 0.12)';
                tbAutoSaveIndicator.style.color = '#2563eb';
                tbAutoSaveIndicator.style.cursor = 'default';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-pen-to-square';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Unsaved changes';
            } else if (status === 'error') {
                tbAutoSaveIndicator.style.background = 'rgba(239, 68, 68, 0.15)';
                tbAutoSaveIndicator.style.color = '#dc2626';
                tbAutoSaveIndicator.style.cursor = 'pointer';
                if (tbAutoSaveIcon) tbAutoSaveIcon.className = 'fa-solid fa-triangle-exclamation';
                if (tbAutoSaveText) tbAutoSaveText.textContent = 'Save failed - retry';
            }
        }
        if (panAutoSaveStatus) {
            if (status === 'saving') {
                panAutoSaveStatus.style.background = 'rgba(234, 179, 8, 0.18)';
                panAutoSaveStatus.style.color = '#b45309';
                panAutoSaveStatus.style.borderColor = 'rgba(234, 179, 8, 0.35)';
                panAutoSaveStatus.style.cursor = 'default';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-arrows-rotate fa-spin"></i> Auto-saving...';
            } else if (status === 'saved') {
                panAutoSaveStatus.style.background = 'rgba(16, 185, 129, 0.15)';
                panAutoSaveStatus.style.color = '#059669';
                panAutoSaveStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                panAutoSaveStatus.style.cursor = 'default';
                const text = detailText || 'All changes saved';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> ' + text;
            } else if (status === 'modified') {
                panAutoSaveStatus.style.background = 'rgba(59, 130, 246, 0.15)';
                panAutoSaveStatus.style.color = '#1d4ed8';
                panAutoSaveStatus.style.borderColor = 'rgba(59, 130, 246, 0.3)';
                panAutoSaveStatus.style.cursor = 'default';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Editing...';
            } else if (status === 'error') {
                panAutoSaveStatus.style.background = 'rgba(239, 68, 68, 0.15)';
                panAutoSaveStatus.style.color = '#b91c1c';
                panAutoSaveStatus.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                panAutoSaveStatus.style.cursor = 'pointer';
                panAutoSaveStatus.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Save failed - retry';
            }
        }
    }

    if (tbAutoSaveIndicator) {
        tbAutoSaveIndicator.addEventListener('click', () => {
            if (tbAutoSaveText && tbAutoSaveText.textContent.includes('retry')) {
                triggerAutoSave(0);
            }
        });
    }
    if (panAutoSaveStatus) {
        panAutoSaveStatus.addEventListener('click', () => {
            if (panAutoSaveStatus.textContent.includes('retry')) {
                triggerAutoSave(0);
            }
        });
    }

    function normalizeTextForDiff(text) {
        if (!text) return "";
        return String(text)
            .normalize("NFC")
            .replace(/\u00a0/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function isLatinScript(text) {
        if (!text) return true;
        // Non-Latin detection: Arabic, Devanagari, Gujarati, CJK, Cyrillic, Thai, Hebrew, etc.
        return !/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0900-\u097F\u0A80-\u0AFF\u4E00-\u9FFF\u3040-\u30FF\u0400-\u04FF\u0E00-\u0E7F\u0590-\u05FF]/.test(text);
    }

    function extractBlockText(el) {
        if (!el) return '';
        // If attached to live DOM and has no badges/toolbars, el.innerText preserves all \n natively
        const badges = el.querySelectorAll('.block-overflow-badge, .docedit-readonly-badge, .docedit-block-toolbar, [data-badge], [contenteditable="false"]');
        if (badges.length === 0 && el.isConnected) {
            let txt = (el.innerText || '').replace(/\r\n/g, '\n');
            txt = txt.replace(/\n\s*\+\d+%\s*$/g, '').trim();
            return txt;
        }

        // When badges exist, clone and ensure line break elements (<br>, <div>, <p>) are converted to \n
        const clone = el.cloneNode(true);
        clone.querySelectorAll('.block-overflow-badge, .docedit-readonly-badge, .docedit-block-toolbar, [data-badge], [contenteditable="false"]').forEach(n => n.remove());
        clone.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
        clone.querySelectorAll('div, p').forEach(d => {
            d.before('\n');
        });
        let txt = (clone.textContent || '').replace(/\r\n/g, '\n');
        txt = txt.replace(/\n\s*\+\d+%\s*$/g, '').trim();
        return txt;
    }

    function isBlockTrulyModified(b) {
        if (!b) return false;
        if (b.is_readonly) return false;
        if (b.text && !isLatinScript(b.text)) return false;
        if (b.orig_text && !isLatinScript(b.orig_text)) return false;
        if (b.is_moved || b.is_deleted || b.is_new) return true;
        if (b.orig_text !== undefined) {
            const cleanCurr = (b.text || '').replace(/\n\s*\+\d+%\s*$/g, '').trim();
            const cleanOrig = (b.orig_text || '').replace(/\n\s*\+\d+%\s*$/g, '').trim();
            const charsCurr = cleanCurr.replace(/\s+/g, '');
            const charsOrig = cleanOrig.replace(/\s+/g, '');
            // If non-whitespace characters differ or normalized text differs:
            if (charsCurr !== charsOrig && normalizeTextForDiff(cleanCurr) !== normalizeTextForDiff(cleanOrig)) {
                return true;
            }
            if (b.orig_is_bold !== undefined && Boolean(b.is_bold) !== Boolean(b.orig_is_bold)) return true;
            if (b.orig_is_italic !== undefined && Boolean(b.is_italic) !== Boolean(b.orig_is_italic)) return true;
            if (b.orig_is_underline !== undefined && Boolean(b.is_underline) !== Boolean(b.orig_is_underline)) return true;
            if (b.font_name && b.orig_font_name) {
                const f1 = b.font_name.trim().toLowerCase().replace(/[\s\-_]|bold|italic|regular|mt|ps/g, '');
                const f2 = b.orig_font_name.trim().toLowerCase().replace(/[\s\-_]|bold|italic|regular|mt|ps/g, '');
                if (f1 && f2 && f1 !== f2) return true;
            }
            if (b.font_size_pt && b.orig_font_size_pt && Math.abs(b.font_size_pt - b.orig_font_size_pt) > 0.1) return true;
            return false;
        }
        return Boolean(b.is_modified);
    }

    function syncBlocksFromDom() {
        if (currentMode !== 'layout_preserved' || !currentPagesData || currentPagesData.length === 0) return;
        currentPagesData.forEach(p => {
            if (!p.blocks) return;
            p.blocks.forEach(b => {
                const el = document.querySelector(`.docedit-text-block[data-block-id="${b.id}"]`);
                if (!el) return;
                const newText = extractBlockText(el);
                if (b.orig_text !== undefined) {
                    const cleanNew = newText.replace(/\n\s*\+\d+%\s*$/g, '').trim();
                    const cleanOrig = b.orig_text.replace(/\n\s*\+\d+%\s*$/g, '').trim();
                    if (cleanNew.replace(/\s+/g, '') === cleanOrig.replace(/\s+/g, '')) {
                        b.text = b.orig_text;
                    } else {
                        b.text = newText;
                    }
                } else {
                    b.text = newText;
                }
                if (el.hasAttribute('data-font-size-pt')) {
                    const parsedSize = parseFloat(el.getAttribute('data-font-size-pt'));
                    if (!isNaN(parsedSize)) {
                        b.font_size_pt = parsedSize;
                    }
                }
                if (b.is_moved) {
                    const srcX = parseFloat(el.style.getPropertyValue('--x-src'));
                    const srcY = parseFloat(el.style.getPropertyValue('--y-src'));
                    if (!isNaN(srcX)) {
                        b.render_x = srcX;
                        b.left_pct = Math.round((srcX / Math.max(1, p.width)) * 100000) / 1000;
                    }
                    if (!isNaN(srcY)) {
                        b.render_y = srcY;
                        b.top_pct = Math.round((srcY / Math.max(1, p.height)) * 100000) / 1000;
                    }
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

                b.is_modified = isBlockTrulyModified(b);
                if (b.is_modified) {
                    el.classList.add('is-edited');
                } else {
                    el.classList.remove('is-edited');
                }

                // Recalculate bbox only if user actually moved the block
                if (b.is_moved) {
                    const lx0 = (b.left_pct / 100.0) * p.width;
                    const ly0 = (b.top_pct / 100.0) * p.height;
                    const w_pt = ((b.width_pct || 10) / 100.0) * p.width;
                    const h_pt = ((b.height_pct || 2) / 100.0) * p.height;
                    b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_pt) * 10) / 10, Math.round((ly0 + h_pt) * 10) / 10];
                }
            });
        });
    }

    // --------------------------------------------------------------------------
    // Phase 7: Document-Level Command Stack (Undo / Redo)
    // --------------------------------------------------------------------------
    class TextEditCommand {
        constructor(blockId, oldText, newText, isFlow = false, oldHtml = null, newHtml = null) {
            this.blockId = blockId;
            this.oldText = oldText;
            this.newText = newText;
            this.isFlow = isFlow;
            this.oldHtml = oldHtml;
            this.newHtml = newHtml;
        }

        execute() {
            if (this.isFlow) {
                if (editorPaper && this.newHtml !== null) {
                    editorPaper.innerHTML = this.newHtml;
                }
                return;
            }
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                b.text = this.newText;
                b.is_modified = isBlockTrulyModified(b);
            }
            if (el) {
                if (this.newText && this.newText.includes('\n')) {
                    el.innerHTML = this.newText.split('\n').map(l => escapeHtml(l)).join('<br>');
                } else {
                    el.textContent = this.newText;
                }
                if (b) el.classList.toggle('is-edited', b.is_modified);
            }
        }

        undo() {
            if (this.isFlow) {
                if (editorPaper && this.oldHtml !== null) {
                    editorPaper.innerHTML = this.oldHtml;
                }
                return;
            }
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                b.text = this.oldText;
                b.is_modified = isBlockTrulyModified(b);
            }
            if (el) {
                if (this.oldText && this.oldText.includes('\n')) {
                    el.innerHTML = this.oldText.split('\n').map(l => escapeHtml(l)).join('<br>');
                } else {
                    el.textContent = this.oldText;
                }
                if (b) el.classList.toggle('is-edited', b.is_modified);
            }
        }
    }

    class StyleChangeCommand {
        constructor(blockId, oldStyle, newStyle) {
            this.blockId = blockId;
            this.oldStyle = { ...oldStyle };
            this.newStyle = { ...newStyle };
        }

        _apply(style) {
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                if (style.font_name !== undefined) b.font_name = style.font_name;
                if (style.font_size_pt !== undefined) {
                    b.font_size_pt = style.font_size_pt;
                    b.size_src = style.font_size_pt;
                }
                if (style.is_bold !== undefined) b.is_bold = style.is_bold;
                if (style.is_italic !== undefined) b.is_italic = style.is_italic;
                if (style.is_underline !== undefined) b.is_underline = style.is_underline;
                if (style.color !== undefined) b.color = style.color;
                if (style.is_multiline !== undefined) b.is_multiline = style.is_multiline;
                b.is_modified = isBlockTrulyModified(b);
            }
            if (el) {
                if (style.font_name !== undefined) {
                    const isSerif = /times|serif|garamond|georgia|baskerville|caslon|cambria|book|palatino/i.test(style.font_name);
                    el.style.fontFamily = `"${style.font_name}", ${isSerif ? 'serif' : 'sans-serif'}`;
                }
                if (style.font_size_pt !== undefined) {
                    el.setAttribute('data-font-size-pt', String(style.font_size_pt));
                    el.style.setProperty('--size-src', String(style.font_size_pt));
                }
                if (style.is_bold !== undefined) el.style.fontWeight = style.is_bold ? 'bold' : 'normal';
                if (style.is_italic !== undefined) el.style.fontStyle = style.is_italic ? 'italic' : 'normal';
                if (style.is_underline !== undefined) el.style.textDecoration = style.is_underline ? 'underline' : 'none';
                if (style.color !== undefined) {
                    el.style.setProperty('--block-color', style.color);
                    el.style.color = style.color;
                }
                if (style.whiteSpace !== undefined) {
                    el.style.whiteSpace = style.whiteSpace;
                }
                if (b) el.classList.toggle('is-edited', b.is_modified);
            }
            if (activeBlockData && activeBlockData.id === this.blockId) {
                updateToolbarEffectStates();
                if (tbFontSizeSelect && b && b.font_size_pt) {
                    ensureFontSizeInSelect(b.font_size_pt);
                    tbFontSizeSelect.value = String(b.font_size_pt);
                }
                if (panFontSize && b && b.font_size_pt) {
                    panFontSize.textContent = `${b.font_size_pt} pt`;
                }
            }
        }

        execute() {
            this._apply(this.newStyle);
        }

        undo() {
            this._apply(this.oldStyle);
        }
    }

    class NudgeOrMoveCommand {
        constructor(blockId, oldPos, newPos) {
            this.blockId = blockId;
            this.oldPos = { ...oldPos };
            this.newPos = { ...newPos };
        }

        _apply(pos) {
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                b.render_x = pos.render_x;
                b.render_y = pos.render_y;
                b.left_pct = pos.left_pct;
                b.top_pct = pos.top_pct;
                b.is_moved = pos.is_moved;
                if (pos.bbox) b.bbox = [...pos.bbox];
                b.is_modified = isBlockTrulyModified(b);
            }
            if (el) {
                el.style.setProperty('--x-src', String(pos.render_x));
                el.style.setProperty('--y-src', String(pos.render_y));
                if (b) el.classList.toggle('is-edited', b.is_modified);
            }
            updateFloatingToolbarPosition();
        }

        execute() {
            this._apply(this.newPos);
        }

        undo() {
            this._apply(this.oldPos);
        }
    }

    class AddBoxCommand {
        constructor(pageNum, blockData) {
            this.pageNum = pageNum;
            this.blockData = { ...blockData };
        }

        execute() {
            const p = currentPagesData.find(page => page.page_num === this.pageNum);
            if (!p) return;
            this.blockData.is_deleted = false;
            let existingIdx = p.blocks.findIndex(b => b.id === this.blockData.id);
            if (existingIdx === -1) {
                p.blocks.push(this.blockData);
            } else {
                p.blocks[existingIdx] = this.blockData;
            }
            let el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockData.id}"]`);
            if (el) {
                el.style.display = 'block';
            } else {
                const sheet = document.getElementById(`doceditPage_${this.pageNum}`);
                if (sheet) {
                    const overlay = sheet.querySelector('.page-text-overlay');
                    if (overlay) {
                        const fontName = tbFontSelect ? tbFontSelect.value : 'EB Garamond';
                        const fontSize = tbFontSizeSelect ? parseFloat(tbFontSizeSelect.value) : 12;
                        el = createBlockElement(this.blockData, p, fontName, fontSize);
                        overlay.appendChild(el);
                    }
                }
            }
            if (el) {
                setActiveBlock(el, this.blockData, p);
                el.focus();
            }
        }

        undo() {
            const p = currentPagesData.find(page => page.page_num === this.pageNum);
            if (!p) return;
            this.blockData.is_deleted = true;
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockData.id}"]`);
            if (el) {
                el.style.display = 'none';
            }
            if (activeBlockData && activeBlockData.id === this.blockData.id) {
                clearActiveBlock();
            }
        }
    }

    class DeleteBoxCommand {
        constructor(pageNum, blockId) {
            this.pageNum = pageNum;
            this.blockId = blockId;
        }

        execute() {
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                b.is_deleted = true;
                b.is_modified = true;
            }
            if (el) {
                el.style.display = 'none';
            }
            if (activeBlockData && activeBlockData.id === this.blockId) {
                clearActiveBlock();
            }
        }

        undo() {
            const b = findBlockById(this.blockId);
            const el = document.querySelector(`.docedit-text-block[data-block-id="${this.blockId}"]`);
            if (b) {
                b.is_deleted = false;
                b.is_modified = isBlockTrulyModified(b);
            }
            if (el) {
                el.style.display = 'block';
                const p = currentPagesData.find(page => page.page_num === this.pageNum);
                if (p && b) {
                    setActiveBlock(el, b, p);
                }
            }
        }
    }

    class BatchCommand {
        constructor(commands = [], label = '') {
            this.commands = commands;
            this.label = label;
        }

        execute() {
            this.commands.forEach(cmd => cmd.execute());
        }

        undo() {
            for (let i = this.commands.length - 1; i >= 0; i--) {
                this.commands[i].undo();
            }
        }
    }

    const docCommandStack = {
        undoStack: [],
        redoStack: [],
        maxSize: 100,

        execute(cmd) {
            cmd.execute();
            this.undoStack.push(cmd);
            if (this.undoStack.length > this.maxSize) {
                this.undoStack.shift();
            }
            this.redoStack = [];
            this.updateButtons();
            triggerAutoSave(200);
            updateThumbnailsSidebar();
            updateIssuesPanel();
        },

        pushExecuted(cmd) {
            this.undoStack.push(cmd);
            if (this.undoStack.length > this.maxSize) {
                this.undoStack.shift();
            }
            this.redoStack = [];
            this.updateButtons();
            triggerAutoSave(200);
            updateThumbnailsSidebar();
            updateIssuesPanel();
        },

        undo() {
            if (this.undoStack.length === 0) return;
            const cmd = this.undoStack.pop();
            cmd.undo();
            this.redoStack.push(cmd);
            this.updateButtons();
            triggerAutoSave(150);
            updateThumbnailsSidebar();
            updateIssuesPanel();
        },

        redo() {
            if (this.redoStack.length === 0) return;
            const cmd = this.redoStack.pop();
            cmd.execute();
            this.undoStack.push(cmd);
            this.updateButtons();
            triggerAutoSave(150);
            updateThumbnailsSidebar();
            updateIssuesPanel();
        },

        canUndo() {
            return this.undoStack.length > 0;
        },

        canRedo() {
            return this.redoStack.length > 0;
        },

        updateButtons() {
            if (tbBtnUndo) tbBtnUndo.disabled = !this.canUndo();
            if (tbBtnRedo) tbBtnRedo.disabled = !this.canRedo();
        },

        clear() {
            this.undoStack = [];
            this.redoStack = [];
            this.updateButtons();
        }
    };

    function findBlockById(blockId) {
        if (!currentPagesData) return null;
        for (const p of currentPagesData) {
            if (!p.blocks) continue;
            for (const b of p.blocks) {
                if (b.id === blockId) return b;
            }
        }
        return null;
    }

    function clearActiveBlock() {
        if (activeBlockEl) {
            activeBlockEl.classList.remove('is-focused', 'is-selected');
        }
        activeBlockEl = null;
        activeBlockData = null;
        activeBlockPage = null;
        if (floatingBlockToolbar) {
            floatingBlockToolbar.style.display = 'none';
        }
        if (tbBtnDeleteBox) tbBtnDeleteBox.style.display = 'none';
        if (tbBtnApplyAll) tbBtnApplyAll.style.display = 'none';
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
                    version: docVersion + 1,
                    font_name: fontName,
                    font_size_pt: fontSize,
                    export_format: chosenFormat,
                    html_content: editorPaper.innerHTML,
                };

                if (currentMode === 'layout_preserved' && currentPagesData && currentPagesData.length > 0) {
                    const changedBlocks = [];
                    currentPagesData.forEach((p, pIdx) => {
                        if (!p.blocks) return;
                        const pNum = p.page_number || (pIdx + 1);
                        p.blocks.forEach(b => {
                            if (b.is_modified || b.is_moved || b.is_deleted || b.is_new) {
                                changedBlocks.push({
                                    id: b.id,
                                    page_num: pNum,
                                    text: b.text,
                                    font_name: b.font_name,
                                    font_size_pt: b.font_size_pt,
                                    size_src: b.size_src,
                                    is_bold: Boolean(b.is_bold),
                                    is_italic: Boolean(b.is_italic),
                                    is_underline: Boolean(b.is_underline),
                                    render_x: b.render_x,
                                    render_y: b.render_y,
                                    left_pct: b.left_pct,
                                    top_pct: b.top_pct,
                                    width_pct: b.width_pct,
                                    height_pct: b.height_pct,
                                    bbox: b.bbox,
                                    is_modified: Boolean(b.is_modified),
                                    is_moved: Boolean(b.is_moved),
                                    is_deleted: Boolean(b.is_deleted),
                                    is_new: Boolean(b.is_new),
                                    font_info: b.font_info,
                                });
                            }
                        });
                    });
                    payload.changed_blocks = changedBlocks;
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
                    if (resData.version) {
                        docVersion = resData.version;
                    }
                    const savedDate = resData.saved_at ? new Date(resData.saved_at * 1000) : new Date();
                    const hh = String(savedDate.getHours()).padStart(2, '0');
                    const mm = String(savedDate.getMinutes()).padStart(2, '0');
                    const ss = String(savedDate.getSeconds()).padStart(2, '0');
                    const savedTimeStr = `Saved ${hh}:${mm}:${ss}`;
                    setAutoSaveStatus('saved', savedTimeStr);
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
        const preprocessSelect = document.getElementById('doceditPreprocessProfile');
        if (preprocessSelect) {
            formData.append('ocr_preprocess_profile', preprocessSelect.value);
        }
        const deskewCheck = document.getElementById('doceditDeskew');
        if (deskewCheck) {
            formData.append('ocr_deskew', deskewCheck.checked ? 'true' : 'false');
        }
        const dewarpCheck = document.getElementById('doceditDewarp');
        if (dewarpCheck) {
            formData.append('ocr_dewarp', dewarpCheck.checked ? 'true' : 'false');
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
        if (data.version) {
            docVersion = data.version;
        }
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
            panAltText.innerHTML = `Original font: <strong>${escapeHtml(font.alternative_to || 'Unknown')}</strong>.<br>` +
                                   `Nearest match: <strong>${escapeHtml(font.name || '')}</strong> (${escapeHtml(font.nearest_match_reason || 'Free equivalent')}).`;
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
        const fuzzyList = (data.fuzzy_words || []).filter(w => !w.is_readonly && isLatinScript(w.text));
        reviewWordsList = fuzzyList.slice();
        panFuzzyCount.textContent = fuzzyList.length;
        if (tbReviewQueueCount) tbReviewQueueCount.textContent = fuzzyList.length;
        panFuzzyList.innerHTML = '';
        if (fuzzyList.length > 0) {
            fuzzyList.slice(0, 25).forEach((fw, idx) => {
                const item = document.createElement('div');
                item.className = 'fuzzy-review-item';
                item.innerHTML = `<span>"${escapeHtml(fw.text)}"</span> <span class="fuzzy-conf-tag">${fw.conf}% conf</span>`;
                item.title = 'Click to open review queue at this word';
                item.addEventListener('click', () => {
                    openReviewQueue();
                    selectReviewWord(idx);
                });
                panFuzzyList.appendChild(item);
            });
        } else {
            panFuzzyList.innerHTML = '<div style="opacity:0.6; font-size:0.8rem; padding:0.3rem;">No suspicious fuzzy characters detected.</div>';
        }
    }

    function loadDocumentIntoEditor(data) {
        // Inject font CSS dynamically for ALL document fonts
        const allCss = ((data.all_fonts_css || '') + '\n' + (data.editor_font_css || '')).trim();
        if (allCss) {
            let styleTag = document.getElementById('doceditPageFonts');
            if (!styleTag) {
                styleTag = document.createElement('style');
                styleTag.id = 'doceditPageFonts';
                document.head.appendChild(styleTag);
            }
            styleTag.textContent = allCss;
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
            editorPaper.classList.add('is-layout-mode');
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
            editorPaper.classList.remove('is-layout-mode');
            if (tbPageNavGroup) tbPageNavGroup.style.display = 'none';
            if (tbPageSep) tbPageSep.style.display = 'none';
            if (tbLayoutAlignSep) tbLayoutAlignSep.style.display = 'none';
            if (tbLayoutAlignGroup) tbLayoutAlignGroup.style.display = 'none';
            if (data.document_html) {
                editorPaper.innerHTML = sanitizeHtml(data.document_html);
            }
            attachFuzzyWordTooltips();
        }

        if (isHeatmapActive) {
            updateHeatmapTiers();
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
            canvas.style.setProperty('--page-width', String(p.width || 595.0));

            const updateCanvasScale = () => {
                const w = canvas.clientWidth || (sheet ? sheet.clientWidth : 708);
                if (w > 0 && p.width > 0) {
                    canvas.style.setProperty('--scale', (w / p.width).toFixed(6));
                }
            };
            setTimeout(updateCanvasScale, 30);

            if ('ResizeObserver' in window) {
                const ro = new ResizeObserver(entries => {
                    for (const entry of entries) {
                        const w = entry.contentRect.width;
                        if (w > 0 && p.width > 0) {
                            canvas.style.setProperty('--scale', (w / p.width).toFixed(6));
                        }
                    }
                });
                ro.observe(canvas);
            }

            const bgImg = document.createElement('img');
            bgImg.className = 'page-bg-img';
            bgImg.src = p.image_url;
            bgImg.alt = `Page ${p.page_num}`;
            bgImg.draggable = false;
            bgImg.addEventListener('load', updateCanvasScale);

            const overlay = document.createElement('div');
            overlay.className = 'page-text-overlay';

            // Alignment guides for magnetic snapping
            // Alignment guides for magnetic snapping
            const guideV = document.createElement('div');
            guideV.className = 'docedit-align-guide-v';
            const guideH = document.createElement('div');
            guideH.className = 'docedit-align-guide-h';

            // Phase 7: Canvas click for Add Box
            canvas.addEventListener('click', (e) => {
                if (isAddingBoxMode) {
                    e.stopPropagation();
                    handleAddBoxClick(e, p, canvas);
                }
            });

            p.blocks.forEach(b => {
                const blockDiv = createBlockElement(b, p, fontName, fontSize);
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
        initThumbnailsSidebar(pages);
        updateIssuesPanel();
        setTimeout(() => {
            zoomFitWidth();
        }, 60);
    }

    function createBlockElement(b, p, fontName, fontSize) {
        if (b.orig_text === undefined) b.orig_text = b.text;
        if (b.orig_font_name === undefined) b.orig_font_name = b.font_name;
        if (b.font_name && b.orig_font_name) {
            const f1 = b.font_name.trim().toLowerCase().replace(/[\s\-_]|bold|italic|regular|mt|ps/g, '');
            const f2 = b.orig_font_name.trim().toLowerCase().replace(/[\s\-_]|bold|italic|regular|mt|ps/g, '');
            if (f1 === f2) {
                b.orig_font_name = b.font_name;
            }
        }
        if (b.orig_font_size_pt === undefined) b.orig_font_size_pt = b.font_size_pt;
        if (b.orig_is_bold === undefined) b.orig_is_bold = Boolean(b.is_bold);
        if (b.orig_is_italic === undefined) b.orig_is_italic = Boolean(b.is_italic);
        if (b.orig_is_underline === undefined) b.orig_is_underline = Boolean(b.is_underline);
        b.is_modified = isBlockTrulyModified(b);

        const isReadonlyBlock = Boolean(b.is_readonly || !isLatinScript(b.text) || !isLatinScript(b.orig_text));
        if (isReadonlyBlock) {
            b.is_readonly = true;
        }

        const blockDiv = document.createElement('div');
        blockDiv.className = `docedit-text-block${isReadonlyBlock ? ' docedit-block-readonly' : ''}${b.has_fuzzy && !isReadonlyBlock ? ' has-fuzzy' : ''}${b.is_modified && !isReadonlyBlock ? ' is-edited' : ''}${b.is_new ? ' is-new-block' : ''}`;
        blockDiv.contentEditable = isReadonlyBlock ? 'false' : 'true';
        blockDiv.spellcheck = false;
        if (isReadonlyBlock) {
            blockDiv.setAttribute('data-readonly', 'true');
            blockDiv.setAttribute('data-readonly-reason', b.readonly_reason || 'Non-Latin script is currently read-only. PyMuPDF does not shape Arabic/Indic scripts or handle RTL.');
            if (b.script) blockDiv.setAttribute('data-script', b.script);
        }
        blockDiv.setAttribute('data-block-id', b.id);
        blockDiv.setAttribute('data-page', p.page_num);
        const bSize = b.size_src || b.font_size_pt || fontSize;
        blockDiv.setAttribute('data-font-size-pt', String(b.font_size_pt || bSize));
        const rot = b.rotation || 0;
        blockDiv.setAttribute('data-rotation', String(rot));
        const bbox = b.orig_bbox || b.bbox || [0, 0, 0, 0];

        let renderX = b.render_x !== undefined ? b.render_x : bbox[0];
        let renderY = b.render_y !== undefined ? b.render_y : bbox[1];
        let renderW = b.render_w !== undefined ? b.render_w : Math.max(1, bbox[2] - bbox[0]);
        let renderH = b.render_h !== undefined ? b.render_h : Math.max(1, bbox[3] - bbox[1]);
        let sizeSrc = b.size_src !== undefined ? b.size_src : (b.font_size_pt || bSize);

        let transformCss = '';
        let transformOriginCss = '';

        if (rot === 90) {
            renderX = bbox[0] || 0;
            renderY = bbox[3] || 0;
            renderW = Math.max(1, (bbox[3] - bbox[1]) || 0);
            renderH = Math.max(1, (bbox[2] - bbox[0]) || 0);
            transformCss = 'rotate(-90deg)';
            transformOriginCss = 'top left';
        } else if (rot === 270) {
            renderX = bbox[2] || 0;
            renderY = bbox[1] || 0;
            renderW = Math.max(1, (bbox[3] - bbox[1]) || 0);
            renderH = Math.max(1, (bbox[2] - bbox[0]) || 0);
            transformCss = 'rotate(90deg)';
            transformOriginCss = 'top left';
        } else if (rot === 180) {
            renderX = bbox[2] || 0;
            renderY = bbox[3] || 0;
            renderW = Math.max(1, (bbox[2] - bbox[0]) || 0);
            renderH = Math.max(1, (bbox[3] - bbox[1]) || 0);
            transformCss = 'rotate(180deg)';
            transformOriginCss = 'top left';
        }

        blockDiv.style.setProperty('--x-src', String(renderX));
        blockDiv.style.setProperty('--y-src', String(renderY));
        blockDiv.style.setProperty('--w-src', String(renderW));
        blockDiv.style.setProperty('--h-src', String(renderH));
        if (b.line_height_src) {
            blockDiv.style.setProperty('--lh-src', String(b.line_height_src));
        }
        blockDiv.style.setProperty('--size-src', String(sizeSrc));

        if (b.color) {
            blockDiv.style.setProperty('--block-color', b.color);
        }

        if (b.is_deleted) {
            blockDiv.style.display = 'none';
        }

        if (transformCss) {
            blockDiv.style.transform = transformCss;
            blockDiv.style.transformOrigin = transformOriginCss;
        }

        const curFName = b.font_name || fontName;
        const isSerif = /times|serif|garamond|georgia|baskerville|caslon|cambria|book|palatino/i.test(curFName);
        const fallbackGeneric = isSerif ? 'serif' : 'sans-serif';
        blockDiv.style.fontFamily = `"${curFName}", ${fallbackGeneric}`;

        if (b.is_bold) blockDiv.style.fontWeight = 'bold';
        if (b.is_italic) blockDiv.style.fontStyle = 'italic';
        if (b.is_underline) blockDiv.style.textDecoration = 'underline';

        if (b.text && b.text.includes('\n')) {
            blockDiv.innerHTML = b.text.split('\n').map(l => escapeHtml(l)).join('<br>');
        } else {
            blockDiv.textContent = b.text;
        }

        if (isReadonlyBlock) {
            const scriptName = b.script || 'Non-Latin';
            const badgeSpan = document.createElement('span');
            badgeSpan.className = 'docedit-readonly-badge';
            badgeSpan.title = b.readonly_reason || 'Non-Latin script is currently read-only. PyMuPDF does not shape Arabic/Indic scripts or handle RTL.';
            badgeSpan.innerHTML = `<i class="fa-solid fa-lock"></i> ${escapeHtml(scriptName.charAt(0).toUpperCase() + scriptName.slice(1))} (Read-Only)`;
            blockDiv.appendChild(badgeSpan);
        }

        // Phase 4: Font substitution warning
        if (b.font_info && !b.font_info.is_exact) {
            try {
                const testCanvas = document.createElement('canvas');
                const testCtx = testCanvas.getContext('2d');
                if (testCtx) {
                    const fontStyle = b.is_italic ? 'italic ' : '';
                    const fontWeight = b.is_bold ? 'bold ' : 'normal ';
                    const fontPt = b.font_size_pt || 12;
                    testCtx.font = `${fontStyle}${fontWeight}${fontPt * 1.333}px "${curFName}", ${fallbackGeneric}`;
                    const origW = (b.orig_bbox && b.orig_bbox[2] > b.orig_bbox[0]) ? (b.orig_bbox[2] - b.orig_bbox[0]) : renderW;
                    if (origW > 10) {
                        const linesToMeasure = (b.lines && b.lines.length > 0) ? b.lines.map(l => l.text) : (b.text || '').split('\n');
                        let maxMeasuredW = 0;
                        linesToMeasure.forEach(lt => {
                            const mw = testCtx.measureText(lt).width * (72.0 / 96.0);
                            if (mw > maxMeasuredW) maxMeasuredW = mw;
                        });
                        if (maxMeasuredW > 0) {
                            const diffPct = Math.abs(maxMeasuredW - origW) / origW;
                            if (diffPct > 0.05) {
                                b.font_metric_warn = true;
                                b.font_metric_diff_pct = Math.round(diffPct * 100);
                                blockDiv.classList.add('has-font-metric-warn');
                                blockDiv.title = `Font substituted (${b.font_info.used}); line width shifted by ~${b.font_metric_diff_pct}%.`;
                            }
                        }
                    }
                }
            } catch (e) {
                console.debug('Metric check error:', e);
            }
        }

        let blockInitialText = b.text || '';
        let typeDebounceTimer = null;

        blockDiv.addEventListener('focus', () => {
            setActiveBlock(blockDiv, b, p);
            blockInitialText = extractBlockText(blockDiv);
            if (isLatinScript(b.text)) {
                blockDiv.spellcheck = true;
                blockDiv.setAttribute('lang', 'en');
            } else {
                blockDiv.spellcheck = false;
                blockDiv.removeAttribute('lang');
            }
        });

        blockDiv.addEventListener('click', (e) => {
            if (isAddingBoxMode) return;
            setActiveBlock(blockDiv, b, p);
        });

        blockDiv.addEventListener('input', () => {
            b.text = extractBlockText(blockDiv);
            b.is_modified = isBlockTrulyModified(b);
            blockDiv.classList.toggle('is-edited', b.is_modified);

            if (isLatinScript(b.text)) {
                blockDiv.spellcheck = true;
                blockDiv.setAttribute('lang', 'en');
            } else {
                blockDiv.spellcheck = false;
                blockDiv.removeAttribute('lang');
            }

            checkBlockOverflow(b, p, blockDiv);
            updateFloatingToolbarPosition();

            clearTimeout(typeDebounceTimer);
            typeDebounceTimer = setTimeout(() => {
                const currText = extractBlockText(blockDiv);
                if (currText !== blockInitialText) {
                    docCommandStack.pushExecuted(new TextEditCommand(b.id, blockInitialText, currText));
                    blockInitialText = currText;
                    updateThumbnailsSidebar();
                    updateIssuesPanel();
                }
            }, 600);

            triggerAutoSave(700);
        });

        blockDiv.addEventListener('blur', () => {
            const currText = extractBlockText(blockDiv);
            if (b.orig_text !== undefined) {
                const cleanCurr = currText.replace(/\n\s*\+\d+%\s*$/g, '').trim();
                const cleanOrig = b.orig_text.replace(/\n\s*\+\d+%\s*$/g, '').trim();
                if (cleanCurr.replace(/\s+/g, '') === cleanOrig.replace(/\s+/g, '')) {
                    b.text = b.orig_text;
                } else {
                    b.text = currText;
                }
            } else {
                b.text = currText;
            }
            blockDiv.classList.remove('is-focused', 'is-selected');
            b.is_modified = isBlockTrulyModified(b);
            blockDiv.classList.toggle('is-edited', b.is_modified);

            if (!b.is_modified && !b.is_new) {
                blockDiv.spellcheck = false;
            } else if (isLatinScript(b.text)) {
                blockDiv.spellcheck = true;
                blockDiv.setAttribute('lang', 'en');
            }

            clearTimeout(typeDebounceTimer);
            if (currText !== blockInitialText) {
                docCommandStack.pushExecuted(new TextEditCommand(b.id, blockInitialText, currText));
                blockInitialText = currText;
                updateThumbnailsSidebar();
                checkBlockOverflow(b, p, blockDiv);
                updateIssuesPanel();
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

        checkBlockOverflow(b, p, blockDiv);
        return blockDiv;
    }

    // Timestamp until which scroll-based page detection is paused (during programmatic smooth scrolling).
    let pageNavLockUntil = 0;

    // Scroll only the editor's own scroll container (never the whole browser window).
    function scrollToSheet(sheet) {
        const wrapper = document.querySelector('.editor-paper-wrapper');
        if (!sheet) return;
        if (!wrapper) {
            sheet.scrollIntoView({ behavior: 'smooth', block: 'start' });
            return;
        }
        pageNavLockUntil = Date.now() + 700;
        const top = sheet.getBoundingClientRect().top - wrapper.getBoundingClientRect().top + wrapper.scrollTop - 12;
        wrapper.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }

    function setupPageScrollObserver() {
        const wrapper = document.querySelector('.editor-paper-wrapper');
        if (!wrapper) return;
        if (wrapper._pageScrollHandler) {
            wrapper.removeEventListener('scroll', wrapper._pageScrollHandler);
        }
        let ticking = false;
        const detectCurrentPage = () => {
            ticking = false;
            if (Date.now() < pageNavLockUntil) return;
            const sheets = wrapper.querySelectorAll('.docedit-page-sheet');
            if (!sheets.length) return;
            const wRect = wrapper.getBoundingClientRect();
            const probe = wRect.top + wRect.height * 0.35;
            let found = null;
            sheets.forEach(s => {
                if (s.getBoundingClientRect().top <= probe) found = s;
            });
            if (!found) found = sheets[0];
            const pNum = parseInt(found.getAttribute('data-page'), 10);
            if (!isNaN(pNum) && pNum !== currentPageIndex) {
                currentPageIndex = pNum;
                updatePageIndicator();
                updateThumbnailsSidebar();
            }
        };
        wrapper._pageScrollHandler = () => {
            if (!ticking) {
                ticking = true;
                requestAnimationFrame(detectCurrentPage);
            }
        };
        wrapper.addEventListener('scroll', wrapper._pageScrollHandler, { passive: true });
    }

    function updatePageIndicator() {
        if (!tbPageIndicator) return;
        const total = currentPagesData.length || 1;
        tbPageIndicator.textContent = `Page ${currentPageIndex} / ${total}`;
    }

    if (tbPagePrev) {
        tbPagePrev.addEventListener('click', () => {
            if (currentPageIndex > 1) {
                currentPageIndex--;
                scrollToSheet(document.getElementById(`doceditPage_${currentPageIndex}`));
                updatePageIndicator();
                updateThumbnailsSidebar();
            }
        });
    }
    if (tbPageNext) {
        tbPageNext.addEventListener('click', () => {
            if (currentPageIndex < (currentPagesData.length || 1)) {
                currentPageIndex++;
                scrollToSheet(document.getElementById(`doceditPage_${currentPageIndex}`));
                updatePageIndicator();
                updateThumbnailsSidebar();
            }
        });
    }

    // --------------------------------------------------------------------------
    // Zoom Controls: fit-width, fit-page, 50%-300% steps, and Ctrl+wheel
    // --------------------------------------------------------------------------
    const ZOOM_STEPS = [50, 75, 90, 100, 125, 150, 175, 200, 250, 300];
    // True while the user is in "Fit Width" mode so the page re-fits on viewport / sidebar resize.
    let fitWidthActive = false;

    function applyZoom(newZoom) {
        fitWidthActive = false;
        currentZoom = Math.max(50, Math.min(300, Math.round(newZoom)));
        if (tbZoomLevel) {
            tbZoomLevel.textContent = `${currentZoom}%`;
        }
        const container = document.querySelector('.docedit-pages-container') || editorPaper;
        if (container) {
            const sheetWidth = Math.round(820 * (currentZoom / 100));
            container.style.setProperty('--docedit-sheet-width', `${sheetWidth}px`);
        }
        // Force update scale on all canvases
        document.querySelectorAll('.page-sheet-canvas').forEach(canvas => {
            const pageNum = canvas.closest('.docedit-page-sheet')?.getAttribute('data-page');
            const pageData = currentPagesData.find(p => String(p.page_num) === String(pageNum));
            const pW = (pageData && pageData.width) ? pageData.width : 595.0;
            const w = canvas.clientWidth;
            if (w > 0 && pW > 0) {
                canvas.style.setProperty('--scale', (w / pW).toFixed(6));
            }
        });
        updateFloatingToolbarPosition();
    }

    function zoomIn() {
        const nextStep = ZOOM_STEPS.find(s => s > currentZoom + 2);
        applyZoom(nextStep !== undefined ? nextStep : currentZoom + 25);
    }

    function zoomOut() {
        const prevSteps = ZOOM_STEPS.filter(s => s < currentZoom - 2);
        const prevStep = prevSteps.length > 0 ? prevSteps[prevSteps.length - 1] : currentZoom - 25;
        applyZoom(prevStep);
    }

    function zoomFitWidth() {
        const wrapper = document.querySelector('.editor-paper-wrapper') || document.querySelector('.editor-stage') || editorPaper;
        if (!wrapper || currentPagesData.length === 0) return;
        const availWidth = Math.max(320, wrapper.clientWidth - 48);
        const targetZoom = Math.round((availWidth / 820) * 100);
        applyZoom(targetZoom);
        fitWidthActive = true;
    }

    let fitResizeTimer = null;
    window.addEventListener('resize', () => {
        if (!fitWidthActive) return;
        clearTimeout(fitResizeTimer);
        fitResizeTimer = setTimeout(() => { if (fitWidthActive) zoomFitWidth(); }, 120);
    });

    function zoomFitPage() {
        const wrapper = document.querySelector('.editor-paper-wrapper') || document.querySelector('.editor-stage') || editorPaper;
        if (!wrapper || currentPagesData.length === 0) return;
        const p = currentPagesData[currentPageIndex - 1] || currentPagesData[0];
        const pW = p.width || 595.0;
        const pH = p.height || 842.0;
        const availHeight = Math.max(300, wrapper.clientHeight - 80);
        const targetWidth = Math.round(availHeight * (pW / pH));
        const targetZoom = Math.round((targetWidth / 820) * 100);
        applyZoom(targetZoom);
    }

    if (tbZoomIn) tbZoomIn.addEventListener('click', zoomIn);
    if (tbZoomOut) tbZoomOut.addEventListener('click', zoomOut);
    if (tbZoomLevel) {
        tbZoomLevel.addEventListener('click', () => applyZoom(100));
    }
    if (tbZoomFitWidth) tbZoomFitWidth.addEventListener('click', zoomFitWidth);
    if (tbZoomFitPage) tbZoomFitPage.addEventListener('click', zoomFitPage);

    // Ctrl + mouse wheel zoom
    window.addEventListener('wheel', (e) => {
        if (e.ctrlKey && currentMode === 'layout_preserved') {
            const inEditor = e.target.closest('.editor-paper-wrapper') || e.target.closest('.editor-stage') || e.target.closest('#editorPaper');
            if (inEditor) {
                e.preventDefault();
                if (e.deltaY < 0) {
                    zoomIn();
                } else {
                    zoomOut();
                }
            }
        }
    }, { passive: false });

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

        const elRect = activeBlockEl.getBoundingClientRect();
        const overlayRect = overlay.getBoundingClientRect();
        if (overlayRect.width > 0 && overlayRect.height > 0) {
            const leftPct = ((elRect.left - overlayRect.left) / overlayRect.width) * 100;
            const topPct = ((elRect.top - overlayRect.top) / overlayRect.height) * 100;
            tb.style.left = `${Math.max(0, leftPct).toFixed(3)}%`;
            tb.style.top = `calc(${Math.max(0, topPct).toFixed(3)}% - 28px)`;
        } else {
            const curL = parseFloat(activeBlockEl.style.left) || (activeBlockData ? activeBlockData.left_pct : 0);
            const curT = parseFloat(activeBlockEl.style.top) || (activeBlockData ? activeBlockData.top_pct : 0);
            tb.style.left = `${curL}%`;
            tb.style.top = `calc(${curT}% - 26px)`;
        }
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

        // Phase 4: Typography & Font Info in Side Panel
        if (panFontName) {
            panFontName.textContent = b.font_name || 'EB Garamond';
        }
        if (panFontSize) {
            panFontSize.textContent = `${b.font_size_pt || 12} pt`;
        }

        const fontInfo = b.font_info;
        if (panFontBadge) {
            if (fontInfo) {
                if (fontInfo.reason === 'embedded') {
                    panFontBadge.className = 'pan-badge badge-embedded';
                    panFontBadge.textContent = 'Embedded Font';
                } else if (fontInfo.is_exact) {
                    panFontBadge.className = 'pan-badge badge-exact';
                    panFontBadge.textContent = fontInfo.reason === 'google_font' ? 'Google Font' : 'Exact Font';
                } else {
                    panFontBadge.className = 'pan-badge badge-alternative';
                    panFontBadge.textContent = 'Nearest Match';
                }
            } else {
                panFontBadge.className = 'pan-badge badge-system';
                panFontBadge.textContent = 'System Font';
            }
        }

        if (panFontResRow && panFontMatchVal) {
            if (fontInfo && fontInfo.requested) {
                panFontResRow.style.display = 'flex';
                panFontMatchVal.textContent = `Original: ${fontInfo.requested} -> Using: ${fontInfo.used || b.font_name} (${fontInfo.reason || 'matched'})`;
            } else {
                panFontResRow.style.display = 'none';
            }
        }

        if (panAltBox && panAltText) {
            if (fontInfo && !fontInfo.is_exact) {
                panAltBox.classList.add('show');
                const reasonText = fontInfo.nearest_match_reason || fontInfo.reason || 'nearest match';
                panAltText.innerHTML = `Original font: <strong>${escapeHtml(fontInfo.requested)}</strong>.<br>` +
                                       `Nearest match: <strong>${escapeHtml(fontInfo.used || b.font_name)}</strong> (${escapeHtml(reasonText)}).`;
            } else {
                panAltBox.classList.remove('show');
            }
        }

        if (panFontMetricAlert && panFontMetricText) {
            if (b.font_metric_warn) {
                panFontMetricAlert.classList.add('show');
                panFontMetricText.textContent = `Line width shifted ~${b.font_metric_diff_pct}% due to font substitution (${fontInfo ? fontInfo.requested : ''} -> ${b.font_name}). Text may reflow or overflow original area.`;
            } else {
                panFontMetricAlert.classList.remove('show');
            }
        }

        const panReadonlyAlert = document.getElementById('panReadonlyAlert');
        const panReadonlyText = document.getElementById('panReadonlyText');
        const isBlockReadonly = Boolean(b.is_readonly || blockDiv.dataset.readonly === 'true' || !isLatinScript(b.text));
        if (panReadonlyAlert) {
            if (isBlockReadonly) {
                panReadonlyAlert.classList.add('show');
                if (panReadonlyText) {
                    panReadonlyText.textContent = b.readonly_reason || blockDiv.dataset.readonlyReason || 'Non-Latin script text is currently read-only to preserve document fidelity. PyMuPDF does not shape Arabic/Indic scripts or handle RTL.';
                }
                if (tbBtnDeleteBox) tbBtnDeleteBox.style.display = 'none';
                if (tbBtnApplyAll) tbBtnApplyAll.style.display = 'none';
            } else {
                panReadonlyAlert.classList.remove('show');
                if (tbBtnDeleteBox) tbBtnDeleteBox.style.display = 'inline-flex';
                if (tbBtnApplyAll) tbBtnApplyAll.style.display = 'inline-flex';
            }
        } else {
            if (tbBtnDeleteBox) tbBtnDeleteBox.style.display = isBlockReadonly ? 'none' : 'inline-flex';
            if (tbBtnApplyAll) tbBtnApplyAll.style.display = isBlockReadonly ? 'none' : 'inline-flex';
        }

        updateToolbarEffectStates();
        updateFloatingToolbarPosition();
    }

    function toggleActiveBlockBold() {
        if (!activeBlockEl || !activeBlockData) return;
        if (activeBlockData.is_readonly || activeBlockEl.dataset.readonly === 'true') {
            showToast('Non-Latin script text is read-only.', 'warning');
            return;
        }
        const oldVal = Boolean(activeBlockData.is_bold);
        const cmd = new StyleChangeCommand(
            activeBlockData.id,
            { is_bold: oldVal },
            { is_bold: !oldVal }
        );
        docCommandStack.execute(cmd);
    }

    function toggleActiveBlockItalic() {
        if (!activeBlockEl || !activeBlockData) return;
        if (activeBlockData.is_readonly || activeBlockEl.dataset.readonly === 'true') {
            showToast('Non-Latin script text is read-only.', 'warning');
            return;
        }
        const oldVal = Boolean(activeBlockData.is_italic);
        const cmd = new StyleChangeCommand(
            activeBlockData.id,
            { is_italic: oldVal },
            { is_italic: !oldVal }
        );
        docCommandStack.execute(cmd);
    }

    function toggleActiveBlockUnderline() {
        if (!activeBlockEl || !activeBlockData) return;
        if (activeBlockData.is_readonly || activeBlockEl.dataset.readonly === 'true') {
            showToast('Non-Latin script text is read-only.', 'warning');
            return;
        }
        const oldVal = Boolean(activeBlockData.is_underline);
        const cmd = new StyleChangeCommand(
            activeBlockData.id,
            { is_underline: oldVal },
            { is_underline: !oldVal }
        );
        docCommandStack.execute(cmd);
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
            const newSrcX = Math.round((newLeft / 100.0) * p.width * 10) / 10;
            const newSrcY = Math.round((newTop / 100.0) * p.height * 10) / 10;
            b.render_x = newSrcX;
            b.render_y = newSrcY;
            activeBlockEl.style.setProperty('--x-src', String(newSrcX));
            activeBlockEl.style.setProperty('--y-src', String(newSrcY));
            b.is_modified = true;
            b.is_moved = true;
            activeBlockEl.classList.add('is-edited');

            updateFloatingToolbarPosition();
        }

        function onMouseUp() {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);

            activeBlockEl.classList.remove('is-moving');
            if (guideV) guideV.style.display = 'none';
            if (guideH) guideH.style.display = 'none';

            // Recalculate bbox in source units
            const lx0 = b.render_x !== undefined ? b.render_x : (b.left_pct / 100.0) * p.width;
            const ly0 = b.render_y !== undefined ? b.render_y : (b.top_pct / 100.0) * p.height;
            const w_src = b.render_w || (((b.width_pct || 10) / 100.0) * p.width);
            const h_src = b.render_h || (((b.height_pct || 2) / 100.0) * p.height);
            b.bbox = [Math.round(lx0 * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((lx0 + w_src) * 10) / 10, Math.round((ly0 + h_src) * 10) / 10];

            if (startLeftPct !== b.left_pct || startTopPct !== b.top_pct) {
                const oldPos = {
                    left_pct: startLeftPct,
                    top_pct: startTopPct,
                    render_x: Math.round((startLeftPct / 100.0) * p.width * 10) / 10,
                    render_y: Math.round((startTopPct / 100.0) * p.height * 10) / 10,
                    is_moved: Boolean(b.is_moved),
                };
                const newPos = {
                    left_pct: b.left_pct,
                    top_pct: b.top_pct,
                    render_x: b.render_x,
                    render_y: b.render_y,
                    bbox: [...b.bbox],
                    is_moved: true,
                };
                docCommandStack.pushExecuted(new NudgeOrMoveCommand(b.id, oldPos, newPos));
            }
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

        const oldPos = {
            render_x: b.render_x !== undefined ? b.render_x : (b.left_pct / 100.0) * p.width,
            render_y: b.render_y !== undefined ? b.render_y : (b.top_pct / 100.0) * p.height,
            left_pct: b.left_pct,
            top_pct: b.top_pct,
            bbox: b.bbox ? [...b.bbox] : null,
            is_moved: Boolean(b.is_moved),
        };

        const newSrcX = Math.round((target.left_pct / 100.0) * p.width * 10) / 10;
        const ly0 = b.render_y !== undefined ? b.render_y : (b.top_pct / 100.0) * p.height;
        const w_src = b.render_w || (((b.width_pct || 10) / 100.0) * p.width);
        const h_src = b.render_h || (((b.height_pct || 2) / 100.0) * p.height);

        const newPos = {
            render_x: newSrcX,
            render_y: ly0,
            left_pct: target.left_pct,
            top_pct: b.top_pct,
            bbox: [Math.round(newSrcX * 10) / 10, Math.round(ly0 * 10) / 10, Math.round((newSrcX + w_src) * 10) / 10, Math.round((ly0 + h_src) * 10) / 10],
            is_moved: true,
        };

        const sheetCanvas = activeBlockEl.closest('.page-sheet-canvas');
        if (sheetCanvas) {
            const guideV = sheetCanvas.querySelector('.docedit-align-guide-v');
            if (guideV) {
                guideV.style.left = `${target.left_pct}%`;
                guideV.style.display = 'block';
                setTimeout(() => { guideV.style.display = 'none'; }, 1000);
            }
        }

        const cmd = new NudgeOrMoveCommand(b.id, oldPos, newPos);
        docCommandStack.execute(cmd);
    }

    function nudgeActiveBlock(dxPct, dyPct) {
        if (!activeBlockEl || !activeBlockData || !activeBlockPage) return;
        if (activeBlockData.is_readonly || activeBlockEl.dataset.readonly === 'true') {
            showToast('Non-Latin script text is read-only.', 'warning');
            return;
        }
        const b = activeBlockData;
        const p = activeBlockPage;

        const oldPos = {
            render_x: b.render_x !== undefined ? b.render_x : (b.left_pct / 100.0) * p.width,
            render_y: b.render_y !== undefined ? b.render_y : (b.top_pct / 100.0) * p.height,
            left_pct: b.left_pct,
            top_pct: b.top_pct,
            bbox: b.bbox ? [...b.bbox] : null,
            is_moved: Boolean(b.is_moved),
        };

        const newLeftPct = Math.max(0, Math.min(100 - (b.width_pct || 1), Math.round((b.left_pct + dxPct) * 1000) / 1000));
        const newTopPct = Math.max(0, Math.min(100 - (b.height_pct || 1), Math.round((b.top_pct + dyPct) * 1000) / 1000));
        const newSrcX = Math.round((newLeftPct / 100.0) * p.width * 10) / 10;
        const newSrcY = Math.round((newTopPct / 100.0) * p.height * 10) / 10;
        const w_src = b.render_w || (((b.width_pct || 10) / 100.0) * p.width);
        const h_src = b.render_h || (((b.height_pct || 2) / 100.0) * p.height);

        const newPos = {
            render_x: newSrcX,
            render_y: newSrcY,
            left_pct: newLeftPct,
            top_pct: newTopPct,
            bbox: [Math.round(newSrcX * 10) / 10, Math.round(newSrcY * 10) / 10, Math.round((newSrcX + w_src) * 10) / 10, Math.round((newSrcY + h_src) * 10) / 10],
            is_moved: true,
        };

        const cmd = new NudgeOrMoveCommand(b.id, oldPos, newPos);
        docCommandStack.execute(cmd);
    }

    // Dismiss active block and floating toolbar on outside click
    document.addEventListener('mousedown', (e) => {
        if (e.target.closest('.docedit-text-block') || e.target.closest('.docedit-block-toolbar') || e.target.closest('.tb-btn') || e.target.closest('.tb-select') || e.target.closest('.docedit-find-replace-panel') || e.target.closest('.docedit-modal') || e.target.closest('.docedit-thumbnails-sidebar') || e.target.closest('.pan-card') || e.target.closest('.editor-statusbar') || e.target.closest('.editor-toolbar')) {
            return;
        }
        if (activeBlockEl) {
            clearActiveBlock();
        }
    });

    // --------------------------------------------------------------------------
    // Phase 7: Overflow Warnings & Side Panel Issues Section
    // --------------------------------------------------------------------------
    function checkBlockOverflow(b, p, blockDiv) {
        if (!b || !p || !blockDiv) return;
        if (b.is_deleted) return;

        // Untouched original blocks from the document must never show false overflow warnings
        if (!b.is_modified && !b.is_new) {
            b.is_overflowing = false;
            b.overflow_pct = 0;
            const existingBadge = blockDiv.querySelector('.block-overflow-badge');
            if (existingBadge) existingBadge.remove();
            blockDiv.classList.remove('has-overflow-warn');
            return;
        }

        const curFName = b.font_name || 'EB Garamond';
        const isSerif = /times|serif|garamond|georgia|baskerville|caslon|cambria|book|palatino/i.test(curFName);
        const fallbackGeneric = isSerif ? 'serif' : 'sans-serif';
        const fontPt = b.font_size_pt || 12;

        const testCanvas = document.createElement('canvas');
        const testCtx = testCanvas.getContext('2d');
        if (!testCtx) return;

        const fontStyle = b.is_italic ? 'italic ' : '';
        const fontWeight = b.is_bold ? 'bold ' : 'normal ';
        testCtx.font = `${fontStyle}${fontWeight}${fontPt * 1.333}px "${curFName}", ${fallbackGeneric}`;

        const lines = (b.text || '').split('\n');
        let maxLineW = 0;
        lines.forEach(line => {
            const w = testCtx.measureText(line).width * (72.0 / 96.0);
            if (w > maxLineW) maxLineW = w;
        });

        const origW = (b.orig_bbox && b.orig_bbox[2] > b.orig_bbox[0]) ? (b.orig_bbox[2] - b.orig_bbox[0]) : (b.render_w || 100);
        const origH = (b.orig_bbox && b.orig_bbox[3] > b.orig_bbox[1]) ? (b.orig_bbox[3] - b.orig_bbox[1]) : (b.render_h || 20);

        let isOverflow = false;
        let overflowPct = 0;

        if (!b.allow_wrap && maxLineW > (origW + 3) && origW > 15) {
            isOverflow = true;
            overflowPct = Math.round(((maxLineW - origW) / origW) * 100);
        }

        const lineH = b.line_height_src || (fontPt * 1.25);
        const totalTextH = lines.length * lineH;
        if (lines.length > 1 && totalTextH > (origH + 4) && origH > 15) {
            isOverflow = true;
            const vertPct = Math.round(((totalTextH - origH) / origH) * 100);
            if (vertPct > overflowPct) overflowPct = vertPct;
        }

        b.is_overflowing = isOverflow;
        b.overflow_pct = overflowPct;

        let badge = blockDiv.querySelector('.block-overflow-badge');
        if (isOverflow && !b.overflow_ignored) {
            blockDiv.classList.add('has-overflow-warn');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'block-overflow-badge';
                badge.contentEditable = 'false';
                badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> +${overflowPct}%`;
                badge.title = `Text overflows bounding box by ~${overflowPct}%. Click to view issues.`;
                badge.addEventListener('mousedown', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setActiveBlock(blockDiv, b, p);
                    if (panIssuesCard) {
                        panIssuesCard.scrollIntoView({ behavior: 'smooth' });
                    }
                });
                blockDiv.appendChild(badge);
            } else {
                badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> +${overflowPct}%`;
                badge.title = `Text overflows bounding box by ~${overflowPct}%. Click to view issues.`;
            }
        } else {
            blockDiv.classList.remove('has-overflow-warn');
            if (badge) badge.remove();
        }
    }

    function updateIssuesPanel() {
        if (!panIssuesCard || !panIssuesList) return;
        if (currentMode !== 'layout_preserved' || !currentPagesData || currentPagesData.length === 0) {
            panIssuesCard.style.display = 'none';
            return;
        }

        const issues = [];
        currentPagesData.forEach(p => {
            if (!p.blocks) return;
            p.blocks.forEach(b => {
                if (b.is_deleted || b.overflow_ignored) return;
                if (b.is_overflowing) {
                    issues.push({
                        type: 'overflow',
                        page: p.page_num,
                        block: b,
                        title: `Page ${p.page_num}: Text Overflow (+${b.overflow_pct || 10}%)`,
                        snippet: b.text || '',
                    });
                } else if (b.font_metric_warn) {
                    issues.push({
                        type: 'font_metric',
                        page: p.page_num,
                        block: b,
                        title: `Page ${p.page_num}: Font Metric Shift (~${b.font_metric_diff_pct || 5}%)`,
                        snippet: b.text || '',
                    });
                }
            });
        });

        if (issues.length === 0) {
            panIssuesCard.style.display = 'none';
            if (panIssuesCount) panIssuesCount.textContent = '0';
            panIssuesList.innerHTML = '';
            return;
        }

        panIssuesCard.style.display = 'block';
        if (panIssuesCount) panIssuesCount.textContent = String(issues.length);
        panIssuesList.innerHTML = '';

        issues.forEach(iss => {
            const item = document.createElement('div');
            item.className = 'pan-issue-item';
            const b = iss.block;
            const pNum = iss.page;
            const shortText = iss.snippet.length > 40 ? (iss.snippet.slice(0, 40) + '...') : iss.snippet;

            item.innerHTML = `
                <div class="pan-issue-header">
                    <span class="pan-issue-title"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(iss.title)}</span>
                </div>
                <div class="pan-issue-snippet">"${escapeHtml(shortText)}"</div>
                <div class="pan-issue-actions">
                    <button type="button" class="pan-issue-btn" data-act="shrink" title="Shrink font size to fit bounding box">Shrink to Fit</button>
                    <button type="button" class="pan-issue-btn" data-act="wrap" title="Allow text to wrap to next line">Allow Wrap</button>
                    <button type="button" class="pan-issue-btn" data-act="ignore" title="Ignore this warning">Ignore</button>
                </div>
            `;

            item.addEventListener('click', (e) => {
                const btn = e.target.closest('.pan-issue-btn');
                if (btn) {
                    e.stopPropagation();
                    const act = btn.getAttribute('data-act');
                    if (act === 'shrink') {
                        const curFName = b.font_name || 'EB Garamond';
                        const isSerif = /times|serif|garamond|georgia|baskerville|caslon|cambria|book|palatino/i.test(curFName);
                        const fallbackGeneric = isSerif ? 'serif' : 'sans-serif';
                        const fontPt = b.font_size_pt || 12;
                        const testCanvas = document.createElement('canvas');
                        const testCtx = testCanvas.getContext('2d');
                        if (testCtx) {
                            testCtx.font = `${fontPt * 1.333}px "${curFName}", ${fallbackGeneric}`;
                            const lines = (b.text || '').split('\n');
                            let maxLineW = 0;
                            lines.forEach(line => {
                                const w = testCtx.measureText(line).width * (72.0 / 96.0);
                                if (w > maxLineW) maxLineW = w;
                            });
                            const origW = (b.orig_bbox && b.orig_bbox[2] > b.orig_bbox[0]) ? (b.orig_bbox[2] - b.orig_bbox[0]) : (b.render_w || 100);
                            if (maxLineW > origW && origW > 10) {
                                const ratio = origW / maxLineW;
                                const newSize = Math.max(6, Math.floor((fontPt * ratio) * 2) / 2);
                                docCommandStack.execute(new StyleChangeCommand(b.id, { font_size_pt: fontPt }, { font_size_pt: newSize }));
                            }
                        }
                    } else if (act === 'wrap') {
                        b.allow_wrap = true;
                        docCommandStack.execute(new StyleChangeCommand(b.id, { whiteSpace: 'nowrap', is_multiline: false }, { whiteSpace: 'normal', is_multiline: true }));
                    } else if (act === 'ignore') {
                        b.overflow_ignored = true;
                        b.is_overflowing = false;
                        const el = document.querySelector(`.docedit-text-block[data-block-id="${b.id}"]`);
                        if (el) el.classList.remove('has-overflow-warn');
                        const badge = el ? el.querySelector('.block-overflow-badge') : null;
                        if (badge) badge.remove();
                        updateIssuesPanel();
                    }
                    return;
                }

                // Click on item jumps to block in editor
                const p = currentPagesData.find(page => page.page_num === pNum);
                const el = document.querySelector(`.docedit-text-block[data-block-id="${b.id}"]`);
                if (el && p) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setActiveBlock(el, b, p);
                    el.focus();
                }
            });

            panIssuesList.appendChild(item);
        });
    }

    // --------------------------------------------------------------------------
    // Phase 7: Add & Delete Text Boxes
    // --------------------------------------------------------------------------
    function toggleAddBoxMode() {
        if (currentMode !== 'layout_preserved') {
            alert('Adding text boxes is available in layout-preserved document mode.');
            return;
        }
        isAddingBoxMode = !isAddingBoxMode;
        if (isAddingBoxMode) {
            if (tbBtnAddBox) tbBtnAddBox.classList.add('active');
            document.body.classList.add('docedit-adding-box');
        } else {
            cancelAddingBoxMode();
        }
    }

    function cancelAddingBoxMode() {
        isAddingBoxMode = false;
        if (tbBtnAddBox) tbBtnAddBox.classList.remove('active');
        document.body.classList.remove('docedit-adding-box');
    }

    function handleAddBoxClick(e, p, canvas) {
        if (!isAddingBoxMode) return;
        const rect = canvas.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickY = e.clientY - rect.top;
        if (clickX < 0 || clickY < 0 || clickX > rect.width || clickY > rect.height) return;

        const leftPct = (clickX / rect.width) * 100;
        const topPct = (clickY / rect.height) * 100;
        const renderX = Math.round(((leftPct / 100.0) * p.width) * 10) / 10;
        const renderY = Math.round(((topPct / 100.0) * p.height) * 10) / 10;

        let inheritedFont = tbFontSelect ? tbFontSelect.value : 'EB Garamond';
        let inheritedSize = tbFontSizeSelect ? parseFloat(tbFontSizeSelect.value) : 12;
        let inheritedColor = '#111827';

        if (p.blocks && p.blocks.length > 0) {
            const activeBlocks = p.blocks.filter(blk => !blk.is_deleted);
            if (activeBlocks.length > 0) {
                activeBlocks.sort((a, b) => {
                    const distA = Math.hypot((a.left_pct || 0) - leftPct, (a.top_pct || 0) - topPct);
                    const distB = Math.hypot((b.left_pct || 0) - leftPct, (b.top_pct || 0) - topPct);
                    return distA - distB;
                });
                const nearest = activeBlocks[0];
                if (nearest.font_name) inheritedFont = nearest.font_name;
                if (nearest.font_size_pt) inheritedSize = nearest.font_size_pt;
                if (nearest.color) inheritedColor = nearest.color;
            }
        }

        const newBlockId = 'b_new_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
        const boxWidth = 140;
        const boxHeight = 26;
        const newBlock = {
            id: newBlockId,
            page_num: p.page_num,
            text: 'New text',
            orig_text: '',
            font_name: inheritedFont,
            orig_font_name: inheritedFont,
            font_size_pt: inheritedSize,
            orig_font_size_pt: inheritedSize,
            size_src: inheritedSize,
            color: inheritedColor,
            render_x: renderX,
            render_y: renderY,
            render_w: boxWidth,
            render_h: boxHeight,
            left_pct: Math.round(leftPct * 1000) / 1000,
            top_pct: Math.round(topPct * 1000) / 1000,
            width_pct: Math.round((boxWidth / p.width) * 100000) / 1000,
            height_pct: Math.round((boxHeight / p.height) * 100000) / 1000,
            bbox: [renderX, renderY, renderX + boxWidth, renderY + boxHeight],
            orig_bbox: [renderX, renderY, renderX + boxWidth, renderY + boxHeight],
            is_new: true,
            is_modified: true,
            is_deleted: false,
        };

        cancelAddingBoxMode();
        docCommandStack.execute(new AddBoxCommand(p.page_num, newBlock));
    }

    function deleteActiveBlock() {
        if (!activeBlockData || !activeBlockPage) return;
        if (activeBlockData.is_readonly || (activeBlockEl && activeBlockEl.dataset.readonly === 'true')) {
            showToast('Non-Latin script text is read-only and cannot be deleted.', 'warning');
            return;
        }
        const b = activeBlockData;
        const p = activeBlockPage;
        const cmd = new DeleteBoxCommand(p.page_num, b.id);
        docCommandStack.execute(cmd);
    }

    // --------------------------------------------------------------------------
    // Phase 7: Document-Wide Find & Replace
    // --------------------------------------------------------------------------
    function openFindReplacePanel() {
        if (!doceditFindReplacePanel) return;
        doceditFindReplacePanel.classList.add('show');
        if (frSearchInput) {
            frSearchInput.focus();
            frSearchInput.select();
        }
        performFind();
    }

    function closeFindReplacePanel() {
        if (!doceditFindReplacePanel) return;
        doceditFindReplacePanel.classList.remove('show');
        clearFindHighlights();
    }

    function clearFindHighlights() {
        findMatches = [];
        currentMatchIndex = -1;
        if (frMatchCount) frMatchCount.textContent = '0 matches';
        if (frResultsList) frResultsList.innerHTML = '';
        document.querySelectorAll('.docedit-find-match, .find-current-match').forEach(el => {
            el.classList.remove('docedit-find-match', 'find-current-match');
        });
    }

    function performFind() {
        clearFindHighlights();
        if (!frSearchInput) return;
        const query = frSearchInput.value;
        if (!query) return;

        const matchCase = frMatchCase ? frMatchCase.checked : false;
        const wholeWord = frWholeWord ? frWholeWord.checked : false;
        const pageOnly = frPageOnly ? frPageOnly.checked : false;

        let regexFlags = matchCase ? 'g' : 'gi';
        let escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (wholeWord) {
            escapedQuery = `\\b${escapedQuery}\\b`;
        }
        let rx;
        try {
            rx = new RegExp(escapedQuery, regexFlags);
        } catch (e) {
            return;
        }

        const matches = [];

        if (currentMode === 'layout_preserved' && currentPagesData) {
            currentPagesData.forEach(p => {
                if (pageOnly && p.page_num !== currentPageIndex) return;
                if (!p.blocks) return;
                p.blocks.forEach(b => {
                    if (b.is_deleted) return;
                    const text = b.text || '';
                    let m;
                    rx.lastIndex = 0;
                    while ((m = rx.exec(text)) !== null) {
                        matches.push({
                            pageNum: p.page_num,
                            blockId: b.id,
                            matchIndex: m.index,
                            matchLength: m[0].length,
                            matchedText: m[0],
                            snippet: text,
                        });
                        if (m.index === rx.lastIndex) rx.lastIndex++;
                    }
                });
            });
        } else if (editorPaper) {
            const text = editorPaper.innerText || '';
            let m;
            rx.lastIndex = 0;
            while ((m = rx.exec(text)) !== null) {
                matches.push({
                    pageNum: 1,
                    blockId: null,
                    matchIndex: m.index,
                    matchLength: m[0].length,
                    matchedText: m[0],
                    snippet: text.slice(Math.max(0, m.index - 20), Math.min(text.length, m.index + m[0].length + 20)),
                });
                if (m.index === rx.lastIndex) rx.lastIndex++;
            }
        }

        findMatches = matches;
        if (matches.length > 0) {
            currentMatchIndex = 0;
            if (frMatchCount) frMatchCount.textContent = `1 of ${matches.length}`;
            highlightAndScrollToMatch(0);
        } else {
            currentMatchIndex = -1;
            if (frMatchCount) frMatchCount.textContent = '0 matches';
        }

        renderFindResultsList();
    }

    function renderFindResultsList() {
        if (!frResultsList) return;
        frResultsList.innerHTML = '';
        if (findMatches.length === 0) return;

        const byPage = {};
        findMatches.forEach((m, idx) => {
            if (!byPage[m.pageNum]) byPage[m.pageNum] = [];
            byPage[m.pageNum].push({ ...m, globalIndex: idx });
        });

        Object.keys(byPage).sort((a, b) => parseInt(a, 10) - parseInt(b, 10)).forEach(pNum => {
            const pageMatches = byPage[pNum];
            const grp = document.createElement('div');
            grp.className = 'fr-page-group';
            grp.innerHTML = `<div class="fr-page-title"><i class="fa-solid fa-file-invoice"></i> Page ${pNum} (${pageMatches.length})</div>`;

            pageMatches.forEach(item => {
                const resItem = document.createElement('div');
                resItem.className = `fr-result-item${item.globalIndex === currentMatchIndex ? ' active' : ''}`;
                resItem.setAttribute('data-idx', String(item.globalIndex));
                const s = item.snippet || '';
                const start = Math.max(0, item.matchIndex - 15);
                const end = Math.min(s.length, item.matchIndex + item.matchLength + 15);
                const before = escapeHtml(s.slice(start, item.matchIndex));
                const target = `<mark>${escapeHtml(item.matchedText)}</mark>`;
                const after = escapeHtml(s.slice(item.matchIndex + item.matchLength, end));
                resItem.innerHTML = `<span>...${before}${target}${after}...</span>`;
                resItem.addEventListener('click', () => {
                    highlightAndScrollToMatch(item.globalIndex);
                });
                grp.appendChild(resItem);
            });

            frResultsList.appendChild(grp);
        });
    }

    function highlightAndScrollToMatch(idx) {
        if (idx < 0 || idx >= findMatches.length) return;
        currentMatchIndex = idx;
        const m = findMatches[idx];
        if (frMatchCount) {
            frMatchCount.textContent = `${idx + 1} of ${findMatches.length}`;
        }

        document.querySelectorAll('.fr-result-item').forEach(el => {
            el.classList.toggle('active', el.getAttribute('data-idx') === String(idx));
        });

        if (m.blockId) {
            const blockEl = document.querySelector(`.docedit-text-block[data-block-id="${m.blockId}"]`);
            if (blockEl) {
                const sheet = blockEl.closest('.docedit-page-sheet');
                if (sheet) {
                    sheet.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                const b = findBlockById(m.blockId);
                const p = currentPagesData.find(page => page.page_num === m.pageNum);
                if (b && p) {
                    setActiveBlock(blockEl, b, p);
                }
                blockEl.classList.add('find-current-match');
                setTimeout(() => blockEl.classList.remove('find-current-match'), 1600);
            }
        }
    }

    function findNextMatch() {
        if (findMatches.length === 0) return;
        const nextIdx = (currentMatchIndex + 1) % findMatches.length;
        highlightAndScrollToMatch(nextIdx);
    }

    function findPrevMatch() {
        if (findMatches.length === 0) return;
        const prevIdx = (currentMatchIndex - 1 + findMatches.length) % findMatches.length;
        highlightAndScrollToMatch(prevIdx);
    }

    function replaceCurrentMatch() {
        if (currentMatchIndex < 0 || currentMatchIndex >= findMatches.length) return;
        const m = findMatches[currentMatchIndex];
        const replacement = frReplaceInput ? frReplaceInput.value : '';

        if (m.blockId) {
            const b = findBlockById(m.blockId);
            if (b) {
                const oldText = b.text || '';
                const before = oldText.slice(0, m.matchIndex);
                const after = oldText.slice(m.matchIndex + m.matchLength);
                const newText = before + replacement + after;
                docCommandStack.execute(new TextEditCommand(b.id, oldText, newText));
            }
        }
        performFind();
    }

    function replaceAllMatches() {
        if (findMatches.length === 0) return;
        const replacement = frReplaceInput ? frReplaceInput.value : '';
        const matchCase = frMatchCase ? frMatchCase.checked : false;
        const wholeWord = frWholeWord ? frWholeWord.checked : false;
        const pageOnly = frPageOnly ? frPageOnly.checked : false;
        const query = frSearchInput ? frSearchInput.value : '';
        if (!query) return;

        let flags = matchCase ? 'g' : 'gi';
        let escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (wholeWord) escaped = `\\b${escaped}\\b`;
        const rx = new RegExp(escaped, flags);

        const commands = [];

        if (currentMode === 'layout_preserved' && currentPagesData) {
            currentPagesData.forEach(p => {
                if (pageOnly && p.page_num !== currentPageIndex) return;
                if (!p.blocks) return;
                p.blocks.forEach(b => {
                    if (b.is_deleted) return;
                    const oldText = b.text || '';
                    if (rx.test(oldText)) {
                        rx.lastIndex = 0;
                        const newText = oldText.replace(rx, replacement);
                        if (newText !== oldText) {
                            commands.push(new TextEditCommand(b.id, oldText, newText));
                        }
                    }
                });
            });
        }

        if (commands.length > 0) {
            const batch = new BatchCommand(commands, `Replace All (${commands.length} blocks)`);
            docCommandStack.execute(batch);
            performFind();
        }
    }

    // --------------------------------------------------------------------------
    // Phase 7: Apply to All Blocks with Selected Font
    // --------------------------------------------------------------------------
    function openApplyAllModal() {
        if (!activeBlockData || !activeBlockPage) {
            alert('Please select a text block first to apply its styling to other blocks.');
            return;
        }
        if (activeBlockData.is_readonly || (activeBlockEl && activeBlockEl.dataset.readonly === 'true')) {
            showToast('Cannot apply styling to or from read-only non-Latin text.', 'warning');
            return;
        }
        if (!doceditApplyAllModal) return;

        const srcFont = activeBlockData.font_name || 'EB Garamond';
        const srcSize = activeBlockData.font_size_pt || 12;
        const srcColor = activeBlockData.color || '#111827';

        if (applySourceFont) applySourceFont.textContent = srcFont;
        if (applySourceSize) applySourceSize.textContent = `${srcSize} pt`;
        if (applySourceColor) applySourceColor.textContent = srcColor;

        updateApplyAllMatchCount();
        doceditApplyAllModal.classList.add('show');
    }

    function closeApplyAllModal() {
        if (doceditApplyAllModal) doceditApplyAllModal.classList.remove('show');
    }

    function updateApplyAllMatchCount() {
        if (!activeBlockData) return;
        const srcFont = activeBlockData.font_name || 'EB Garamond';
        const scopeRadio = document.querySelector('input[name="applyScope"]:checked');
        const scope = scopeRadio ? scopeRadio.value : 'all';

        let count = 0;
        if (currentPagesData) {
            currentPagesData.forEach(p => {
                if (scope === 'page' && p.page_num !== activeBlockPage.page_num) return;
                if (!p.blocks) return;
                p.blocks.forEach(b => {
                    if (b.id !== activeBlockData.id && !b.is_deleted && b.font_name === srcFont) {
                        count++;
                    }
                });
            });
        }
        if (applyMatchCount) {
            applyMatchCount.textContent = `${count} other block(s) will be updated.`;
        }
        if (modalBtnConfirmApplyAll) {
            modalBtnConfirmApplyAll.disabled = (count === 0);
        }
    }

    function confirmApplyAllChanges() {
        if (!activeBlockData || !activeBlockPage) return;
        const srcFont = activeBlockData.font_name || 'EB Garamond';
        const srcSize = activeBlockData.font_size_pt || 12;
        const srcColor = activeBlockData.color || '#111827';

        const doFont = applyOptFont ? applyOptFont.checked : true;
        const doSize = applyOptSize ? applyOptSize.checked : true;
        const doColor = applyOptColor ? applyOptColor.checked : true;

        const scopeRadio = document.querySelector('input[name="applyScope"]:checked');
        const scope = scopeRadio ? scopeRadio.value : 'all';

        const commands = [];
        if (currentPagesData) {
            currentPagesData.forEach(p => {
                if (scope === 'page' && p.page_num !== activeBlockPage.page_num) return;
                if (!p.blocks) return;
                p.blocks.forEach(b => {
                    if (b.id !== activeBlockData.id && !b.is_deleted && !b.is_readonly && b.font_name === srcFont) {
                        const oldStyle = {};
                        const newStyle = {};
                        if (doFont) {
                            oldStyle.font_name = b.font_name;
                            newStyle.font_name = srcFont;
                        }
                        if (doSize) {
                            oldStyle.font_size_pt = b.font_size_pt;
                            newStyle.font_size_pt = srcSize;
                        }
                        if (doColor) {
                            oldStyle.color = b.color;
                            newStyle.color = srcColor;
                        }
                        commands.push(new StyleChangeCommand(b.id, oldStyle, newStyle));
                    }
                });
            });
        }

        if (commands.length > 0) {
            const batch = new BatchCommand(commands, `Apply styling to all (${commands.length} blocks)`);
            docCommandStack.execute(batch);
        }

        closeApplyAllModal();
    }

    // --------------------------------------------------------------------------
    // Phase 7: Before / After Render Comparison Mode
    // --------------------------------------------------------------------------
    function toggleBeforeAfter(forceState) {
        if (forceState !== undefined) {
            isBeforeModeActive = forceState;
        } else {
            isBeforeModeActive = !isBeforeModeActive;
        }

        const container = document.querySelector('.docedit-pages-container') || editorPaper;
        if (container) {
            container.classList.toggle('docedit-before-mode', isBeforeModeActive);
        }
        if (doceditBeforeBanner) {
            doceditBeforeBanner.classList.toggle('show', isBeforeModeActive);
        }
        if (tbBtnBeforeAfter) {
            tbBtnBeforeAfter.classList.toggle('active', isBeforeModeActive);
        }
    }

    // --------------------------------------------------------------------------
    // Phase 7: Page Thumbnails Sidebar
    // --------------------------------------------------------------------------
    function toggleThumbnailsSidebar(forceState) {
        if (!doceditThumbnailsSidebar) return;
        const isCollapsed = doceditThumbnailsSidebar.classList.contains('collapsed');
        const shouldCollapse = (forceState !== undefined) ? !forceState : !isCollapsed;
        doceditThumbnailsSidebar.classList.toggle('collapsed', shouldCollapse);
        if (tbBtnThumbnails) {
            tbBtnThumbnails.classList.toggle('active', !shouldCollapse);
        }
        // Sidebar animates its width; re-fit the page once the editor area has settled.
        setTimeout(() => { if (fitWidthActive) zoomFitWidth(); }, 300);
    }

    function initThumbnailsSidebar(pages) {
        if (!thumbList) return;
        thumbList.innerHTML = '';
        if (thumbPageCount) thumbPageCount.textContent = String(pages.length);
        // Multi-page documents get the page strip open by default for quick navigation.
        if (pages.length > 1) toggleThumbnailsSidebar(true);

        pages.forEach(p => {
            const item = document.createElement('div');
            item.className = `thumb-item${p.page_num === currentPageIndex ? ' active' : ''}`;
            item.setAttribute('data-page', String(p.page_num));

            const hasEdits = p.blocks && p.blocks.some(b => b.is_modified || b.is_new || b.is_deleted);
            const hasFuzzy = p.blocks && p.blocks.some(b => b.has_fuzzy);

            item.innerHTML = `
                <div class="thumb-preview-wrap">
                    <img class="thumb-img" src="${p.image_url}" alt="Thumbnail Page ${p.page_num}" loading="lazy" />
                    <div class="thumb-badges">
                        <span class="thumb-badge badge-edited" style="display: ${hasEdits ? 'inline-flex' : 'none'};" title="Has user edits"><i class="fa-solid fa-pen"></i> Edited</span>
                        <span class="thumb-badge badge-fuzzy" style="display: ${hasFuzzy ? 'inline-flex' : 'none'};" title="Has low-confidence OCR text"><i class="fa-solid fa-triangle-exclamation"></i> Low Conf</span>
                    </div>
                </div>
                <div class="thumb-label">Page ${p.page_num}</div>
            `;

            item.addEventListener('click', () => {
                goToPage(p.page_num);
            });

            thumbList.appendChild(item);
        });
    }

    function updateThumbnailsSidebar() {
        if (!thumbList || !currentPagesData) return;
        currentPagesData.forEach(p => {
            const item = thumbList.querySelector(`.thumb-item[data-page="${p.page_num}"]`);
            if (item) {
                item.classList.toggle('active', p.page_num === currentPageIndex);
                const hasEdits = p.blocks && p.blocks.some(b => b.is_modified || b.is_new || b.is_deleted);
                const editedBadge = item.querySelector('.badge-edited');
                if (editedBadge) {
                    editedBadge.style.display = hasEdits ? 'inline-flex' : 'none';
                }
                // Keep the active thumbnail visible inside the strip (scroll the strip only).
                if (p.page_num === currentPageIndex && !doceditThumbnailsSidebar.classList.contains('collapsed')) {
                    const itemTop = item.offsetTop;
                    const itemBottom = itemTop + item.offsetHeight;
                    if (itemTop < thumbList.scrollTop) {
                        thumbList.scrollTop = itemTop - 8;
                    } else if (itemBottom > thumbList.scrollTop + thumbList.clientHeight) {
                        thumbList.scrollTop = itemBottom - thumbList.clientHeight + 8;
                    }
                }
            }
        });
    }

    function goToPage(pageNum) {
        currentPageIndex = pageNum;
        const targetSheet = document.getElementById(`doceditPage_${pageNum}`);
        if (targetSheet) {
            scrollToSheet(targetSheet);
        }
        updatePageIndicator();
        updateThumbnailsSidebar();
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
            const isSerif = /times|serif|garamond|georgia|baskerville|caslon|cambria|book|palatino/i.test(newFont);
            const fallbackGeneric = isSerif ? 'serif' : 'sans-serif';
            editorPaper.style.fontFamily = `"${newFont}", ${fallbackGeneric}`;
            panFontName.textContent = newFont;

            // In layout_preserved mode: if a specific block is active, update only that block
            if (currentMode === 'layout_preserved') {
                if (activeBlockEl && activeBlockData) {
                    const oldFont = activeBlockData.font_name;
                    const cmd = new StyleChangeCommand(
                        activeBlockData.id,
                        { font_name: oldFont },
                        { font_name: newFont }
                    );
                    docCommandStack.execute(cmd);
                }
            } else {
                triggerAutoSave(100);
            }

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

            // In layout_preserved mode: if a specific block is active, update only that block
            if (currentMode === 'layout_preserved') {
                if (activeBlockEl && activeBlockData) {
                    const oldSize = activeBlockData.font_size_pt;
                    const cmd = new StyleChangeCommand(
                        activeBlockData.id,
                        { font_size_pt: oldSize },
                        { font_size_pt: newSizeNum }
                    );
                    docCommandStack.execute(cmd);
                }
            } else {
                triggerAutoSave(100);
            }

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

    async function saveDocumentInPlace() {
        if (!currentSessionId) return;
        if (autoSaveTimeout) {
            clearTimeout(autoSaveTimeout);
            autoSaveTimeout = null;
        }
        syncBlocksFromDom();

        const origTbHtml = tbBtnSave ? tbBtnSave.innerHTML : '';
        const origPanHtml = panBtnSave ? panBtnSave.innerHTML : '';
        if (tbBtnSave) {
            tbBtnSave.disabled = true;
            tbBtnSave.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
        }
        if (panBtnSave) {
            panBtnSave.disabled = true;
            panBtnSave.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
        }
        setAutoSaveStatus('saving');

        try {
            const htmlContent = editorPaper.innerHTML;
            const fontName = tbFontSelect ? tbFontSelect.value : (panFontName.textContent || 'EB Garamond');
            const fontSize = tbFontSizeSelect ? tbFontSizeSelect.value : 12;
            const chosenFormat = (panDownloadFormat ? panDownloadFormat.value : 'pdf') || 'pdf';

            let payload = {
                font_name: fontName,
                font_size_pt: fontSize,
                export_format: chosenFormat,
                is_autosave: false,
                version: docVersion,
            };

            if (currentMode === 'layout_preserved' && currentPagesData.length > 0) {
                syncBlocksFromDom();
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
                setAutoSaveStatus('error');
                if (tbBtnSave) {
                    tbBtnSave.disabled = false;
                    tbBtnSave.innerHTML = origTbHtml;
                }
                if (panBtnSave) {
                    panBtnSave.disabled = false;
                    panBtnSave.innerHTML = origPanHtml;
                }
                return;
            }

            if (data.version) {
                docVersion = data.version;
            }
            const savedDate = new Date();
            const hh = String(savedDate.getHours()).padStart(2, '0');
            const mm = String(savedDate.getMinutes()).padStart(2, '0');
            const ss = String(savedDate.getSeconds()).padStart(2, '0');
            const savedTimeStr = `Saved ${hh}:${mm}:${ss}`;
            setAutoSaveStatus('saved', savedTimeStr);

            if (tbBtnSave) {
                tbBtnSave.disabled = false;
                tbBtnSave.innerHTML = '<i class="fa-solid fa-check"></i> Saved!';
                setTimeout(() => {
                    tbBtnSave.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save';
                }, 2000);
            }
            if (panBtnSave) {
                panBtnSave.disabled = false;
                panBtnSave.innerHTML = '<i class="fa-solid fa-check"></i> Changes Saved!';
                setTimeout(() => {
                    panBtnSave.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Changes';
                }, 2000);
            }

            showNotice(
                'Changes Saved Successfully',
                `All edits saved to session (${savedTimeStr}). You can continue editing or download anytime.`
            );
        } catch (err) {
            console.error('Save error:', err);
            alert('Failed to save document: ' + err.message);
            setAutoSaveStatus('error');
            if (tbBtnSave) {
                tbBtnSave.disabled = false;
                tbBtnSave.innerHTML = origTbHtml;
            }
            if (panBtnSave) {
                panBtnSave.disabled = false;
                panBtnSave.innerHTML = origPanHtml;
            }
        }
    }

    if (tbBtnSave) {
        tbBtnSave.addEventListener('click', (e) => {
            e.preventDefault();
            saveDocumentInPlace();
        });
    }

    if (panBtnSave) {
        panBtnSave.addEventListener('click', (e) => {
            e.preventDefault();
            saveDocumentInPlace();
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
                syncBlocksFromDom();
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

            // Download triggered successfully. Session remains active so user can continue editing.

            // REQUIRED NOTICE: Display success message with note that file has not been saved on server
            if (data.overflow_warnings && data.overflow_warnings.length > 0) {
                showNotice(
                    'Document Downloaded with Overflow Warnings',
                    `${data.overflow_warnings.length} text box(es) may overflow their original boundaries in the exported file. Review the Issues panel for details.`
                );
            } else {
                showNotice(
                    'Document downloaded successfully to your system!',
                    'Your exported file has been downloaded. You can keep editing your document or download again anytime.'
                );
            }

            panBtnDownload.disabled = false;
            panBtnDownload.innerHTML = '<i class="fa-solid fa-circle-check"></i> Downloaded!';
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
        docVersion = 0;
        docCommandStack.clear();
        cancelAddingBoxMode();
        toggleBeforeAfter(false);
        closeFindReplacePanel();
        closeApplyAllModal();
        toggleConfidenceHeatmap(false);
        closeReviewQueue();
        reviewWordsList = [];
        reviewCurrentIndex = -1;
        if (tbReviewQueueCount) tbReviewQueueCount.textContent = '0';
        if (doceditThumbnailsSidebar) doceditThumbnailsSidebar.classList.add('collapsed');
        if (panIssuesCard) panIssuesCard.style.display = 'none';
        if (tbPageNavGroup) tbPageNavGroup.style.display = 'none';
        if (tbPageSep) tbPageSep.style.display = 'none';
        if (tbLayoutAlignSep) tbLayoutAlignSep.style.display = 'none';
        if (tbLayoutAlignGroup) tbLayoutAlignGroup.style.display = 'none';
        if (fileInput) fileInput.value = '';
        editorPaper.contentEditable = "true";
        editorPaper.classList.remove('is-layout-mode');
        fitWidthActive = false;
        editorPaper.innerHTML = '<p></p>';
        workspace.classList.remove('active');
        dropzone.style.display = 'block';
        hideNotice();
    }

    // --------------------------------------------------------------------------
    // Phase 7: Toolbar & UI Event Listeners
    // --------------------------------------------------------------------------
    if (tbBtnUndo) {
        tbBtnUndo.addEventListener('click', (e) => {
            e.preventDefault();
            docCommandStack.undo();
        });
    }

    if (tbBtnRedo) {
        tbBtnRedo.addEventListener('click', (e) => {
            e.preventDefault();
            docCommandStack.redo();
        });
    }

    if (tbBtnFindReplace) {
        tbBtnFindReplace.addEventListener('click', (e) => {
            e.preventDefault();
            openFindReplacePanel();
        });
    }

    if (tbBtnBeforeAfter) {
        tbBtnBeforeAfter.addEventListener('click', (e) => {
            e.preventDefault();
            toggleBeforeAfter();
        });
    }

    if (tbBtnThumbnails) {
        tbBtnThumbnails.addEventListener('click', (e) => {
            e.preventDefault();
            toggleThumbnailsSidebar();
        });
    }

    if (thumbBtnCollapse) {
        thumbBtnCollapse.addEventListener('click', () => {
            toggleThumbnailsSidebar(false);
        });
    }

    if (tbBtnAddBox) {
        tbBtnAddBox.addEventListener('click', (e) => {
            e.preventDefault();
            toggleAddBoxMode();
        });
    }

    if (tbBtnDeleteBox) {
        tbBtnDeleteBox.addEventListener('click', (e) => {
            e.preventDefault();
            deleteActiveBlock();
        });
    }

    if (tbBtnApplyAll) {
        tbBtnApplyAll.addEventListener('click', (e) => {
            e.preventDefault();
            openApplyAllModal();
        });
    }

    // Find & Replace panel listeners
    if (frBtnClose) frBtnClose.addEventListener('click', closeFindReplacePanel);
    if (frBtnNext) frBtnNext.addEventListener('click', findNextMatch);
    if (frBtnPrev) frBtnPrev.addEventListener('click', findPrevMatch);
    if (frBtnReplace) frBtnReplace.addEventListener('click', replaceCurrentMatch);
    if (frBtnReplaceAll) frBtnReplaceAll.addEventListener('click', replaceAllMatches);

    let frDebounceTimer = null;
    if (frSearchInput) {
        frSearchInput.addEventListener('input', () => {
            clearTimeout(frDebounceTimer);
            frDebounceTimer = setTimeout(performFind, 250);
        });
        frSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) findPrevMatch();
                else findNextMatch();
            }
        });
    }

    if (frReplaceInput) {
        frReplaceInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                replaceCurrentMatch();
            }
        });
    }

    if (frMatchCase) frMatchCase.addEventListener('change', performFind);
    if (frWholeWord) frWholeWord.addEventListener('change', performFind);
    if (frPageOnly) frPageOnly.addEventListener('change', performFind);

    // Apply to All modal listeners
    if (modalBtnCloseApplyAll) modalBtnCloseApplyAll.addEventListener('click', closeApplyAllModal);
    if (modalBtnConfirmApplyAll) modalBtnConfirmApplyAll.addEventListener('click', confirmApplyAllChanges);
    if (doceditApplyAllModal) {
        doceditApplyAllModal.addEventListener('click', (e) => {
            if (e.target === doceditApplyAllModal) closeApplyAllModal();
        });
    }
    document.querySelectorAll('input[name="applyScope"]').forEach(radio => {
        radio.addEventListener('change', updateApplyAllMatchCount);
    });
    if (applyOptFont) applyOptFont.addEventListener('change', updateApplyAllMatchCount);
    if (applyOptSize) applyOptSize.addEventListener('change', updateApplyAllMatchCount);
    if (applyOptColor) applyOptColor.addEventListener('change', updateApplyAllMatchCount);

    // --------------------------------------------------------------------------
    // Phase 8: Confidence Heatmap & Fuzzy Review Queue
    // --------------------------------------------------------------------------
    function toggleConfidenceHeatmap(forceState) {
        if (typeof forceState === 'boolean') {
            isHeatmapActive = forceState;
        } else {
            isHeatmapActive = !isHeatmapActive;
        }

        if (isHeatmapActive) {
            editorPaper.classList.add('docedit-heatmap-active');
            if (tbBtnHeatmap) tbBtnHeatmap.classList.add('active');
            if (tbHeatmapControls) tbHeatmapControls.style.display = 'inline-flex';
            updateHeatmapTiers();
        } else {
            editorPaper.classList.remove('docedit-heatmap-active');
            if (tbBtnHeatmap) tbBtnHeatmap.classList.remove('active');
            if (tbHeatmapControls) tbHeatmapControls.style.display = 'none';
        }
    }

    function updateHeatmapTiers() {
        const threshold = parseInt(tbHeatmapSlider ? tbHeatmapSlider.value : 70, 10);
        heatmapThreshold = threshold;
        if (tbHeatmapValue) tbHeatmapValue.textContent = `${threshold}%`;

        const lowCutoff = Math.max(30, threshold - 15);

        const wordEls = editorPaper.querySelectorAll('.ocr-word[data-conf]');
        wordEls.forEach(el => {
            const confVal = parseInt(el.getAttribute('data-conf') || '100', 10);
            if (isNaN(confVal)) return;

            let tier = 'high';
            if (confVal < lowCutoff) {
                tier = 'low';
            } else if (confVal < threshold) {
                tier = 'med';
            } else {
                tier = 'high';
            }
            el.setAttribute('data-conf-tier', tier);
        });
    }

    async function fetchFuzzyWords() {
        if (!currentSessionId) return;
        try {
            const resp = await fetch(`/docedit/api/fuzzy-words/${currentSessionId}/`);
            const data = await resp.json();
            if (data.success) {
                reviewWordsList = (data.fuzzy_words || []).filter(w => !w.is_readonly && isLatinScript(w.text));
                updateReviewStats(data.stats || {
                    total_fuzzy: reviewWordsList.length,
                    reviewed_count: reviewWordsList.filter(w => w.review_status && w.review_status !== 'pending').length,
                    unreviewed_count: reviewWordsList.filter(w => !w.review_status || w.review_status === 'pending').length,
                });
            }
        } catch (e) {
            console.error('Failed to fetch fuzzy words:', e);
        }
    }

    async function openReviewQueue() {
        if (!currentSessionId) return;
        if (doceditReviewQueuePanel) {
            doceditReviewQueuePanel.style.display = 'flex';
            doceditReviewQueuePanel.classList.add('show');
        }
        isReviewQueueOpen = true;

        if (reviewWordsList.length === 0) {
            await fetchFuzzyWords();
        }

        const firstPending = reviewWordsList.findIndex(w => !w.review_status || w.review_status === 'pending');
        if (firstPending >= 0) {
            selectReviewWord(firstPending);
        } else if (reviewWordsList.length > 0) {
            selectReviewWord(0);
        } else {
            renderReviewQueueUI();
        }
    }

    function closeReviewQueue() {
        if (doceditReviewQueuePanel) {
            doceditReviewQueuePanel.style.display = 'none';
            doceditReviewQueuePanel.classList.remove('show');
        }
        isReviewQueueOpen = false;
        clearWordHighlight();
    }

    function selectReviewWord(index) {
        if (index < 0 || index >= reviewWordsList.length) return;
        reviewCurrentIndex = index;
        const word = reviewWordsList[index];

        if (rqWordIndex) rqWordIndex.textContent = `Word ${index + 1} of ${reviewWordsList.length}`;
        if (rqWordConfidence) {
            rqWordConfidence.textContent = `${word.conf}%`;
            rqWordConfidence.className = `rq-word-conf-badge conf-${word.conf_tier || (word.conf < 60 ? 'low' : 'med')}`;
        }
        if (rqFuzzyReasons) {
            const reasons = Array.isArray(word.fuzzy_reasons) ? word.fuzzy_reasons.join(', ') : (word.fuzzy_reasons || 'Flagged for review');
            rqFuzzyReasons.textContent = reasons;
        }

        if (rqWordInput) {
            rqWordInput.value = word.edited_text || word.text;
        }

        if (rqCropImg) {
            rqCropImg.style.display = 'block';
            if (rqCropFallback) rqCropFallback.style.display = 'none';
            rqCropImg.src = `/docedit/api/word-crop/${currentSessionId}/${word.id}/?t=${Date.now()}`;
            rqCropImg.onerror = () => {
                rqCropImg.style.display = 'none';
                if (rqCropFallback) rqCropFallback.style.display = 'block';
            };
        }

        if (word.page_num && currentMode === 'layout_preserved' && currentPageIndex !== word.page_num) {
            goToPage(word.page_num);
        }

        highlightWordOnPage(word);
        renderReviewQueueUI();
    }

    function highlightWordOnPage(word) {
        clearWordHighlight();
        let targetEl = editorPaper.querySelector(`.ocr-word[data-word-id="${word.id}"]`);
        if (!targetEl) {
            const words = editorPaper.querySelectorAll('.ocr-word');
            for (const w of words) {
                if (w.textContent.trim() === word.text) {
                    targetEl = w;
                    break;
                }
            }
        }
        if (targetEl) {
            targetEl.classList.add('ocr-word-focused');
            targetEl.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
    }

    function clearWordHighlight() {
        const prev = editorPaper.querySelectorAll('.ocr-word-focused');
        prev.forEach(p => p.classList.remove('ocr-word-focused'));
    }

    async function acceptCurrentWord() {
        if (reviewCurrentIndex < 0 || reviewCurrentIndex >= reviewWordsList.length) return;
        const word = reviewWordsList[reviewCurrentIndex];
        const newText = rqWordInput ? rqWordInput.value.trim() : word.text;
        const isEdit = (newText && newText !== word.text);
        const action = isEdit ? 'edit' : 'accept';

        await submitWordReview(word.id, action, newText);
        advanceToNextWord();
    }

    async function skipCurrentWord() {
        if (reviewCurrentIndex < 0 || reviewCurrentIndex >= reviewWordsList.length) return;
        const word = reviewWordsList[reviewCurrentIndex];
        await submitWordReview(word.id, 'skip');
        advanceToNextWord();
    }

    function focusEditField() {
        if (rqWordInput) {
            rqWordInput.focus();
            rqWordInput.select();
        }
    }

    function advanceToNextWord() {
        if (reviewWordsList.length === 0) return;
        const nextPending = reviewWordsList.findIndex((w, i) => i > reviewCurrentIndex && (!w.review_status || w.review_status === 'pending'));
        if (nextPending >= 0) {
            selectReviewWord(nextPending);
            return;
        }
        const anyPending = reviewWordsList.findIndex(w => !w.review_status || w.review_status === 'pending');
        if (anyPending >= 0) {
            selectReviewWord(anyPending);
            return;
        }
        renderReviewQueueUI();
    }

    async function submitWordReview(wordId, action, editedText) {
        if (!currentSessionId) return;
        const word = reviewWordsList.find(w => w.id === wordId);
        if (!word) return;

        word.review_status = (action === 'skip' ? 'skipped' : (action === 'edit' ? 'edited' : 'accepted'));
        if (action === 'edit' && editedText) {
            word.edited_text = editedText;
        }

        const el = editorPaper.querySelector(`.ocr-word[data-word-id="${wordId}"]`);
        if (el) {
            if (action === 'edit' && editedText) {
                el.textContent = editedText;
            }
            el.classList.add('reviewed');
        }

        triggerAutoSave();

        try {
            const formData = new FormData();
            formData.append('action', action);
            if (editedText) formData.append('edited_text', editedText);

            const resp = await fetch(`/docedit/api/review-word/${currentSessionId}/${wordId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
                body: formData,
            });
            const data = await resp.json();
            if (data.success && data.stats) {
                updateReviewStats(data.stats);
            }
        } catch (e) {
            console.error('Failed to submit word review:', e);
        }

        renderReviewQueueUI();
    }

    function updateReviewStats(stats) {
        const total = stats.total_fuzzy !== undefined ? stats.total_fuzzy : reviewWordsList.length;
        const reviewed = stats.reviewed_count !== undefined ? stats.reviewed_count : reviewWordsList.filter(w => w.review_status && w.review_status !== 'pending').length;
        const remaining = Math.max(0, total - reviewed);

        if (rqProgressBadge) rqProgressBadge.textContent = `${reviewed} of ${total} reviewed`;
        if (tbReviewQueueCount) tbReviewQueueCount.textContent = remaining;
        if (panFuzzyCount) panFuzzyCount.textContent = remaining;
        if (rqListRemaining) rqListRemaining.textContent = `${remaining} remaining`;

        const pct = total > 0 ? Math.round((reviewed / total) * 100) : 100;
        if (rqProgressBarFill) rqProgressBarFill.style.width = `${pct}%`;

        if (total > 0 && reviewed >= total) {
            if (rqActiveCard) rqActiveCard.style.display = 'none';
            if (rqCompletedState) rqCompletedState.style.display = 'block';
        } else {
            if (rqActiveCard) rqActiveCard.style.display = 'block';
            if (rqCompletedState) rqCompletedState.style.display = 'none';
        }
    }

    function renderReviewQueueUI() {
        if (!doceditReviewQueuePanel || !isReviewQueueOpen) return;

        const total = reviewWordsList.length;
        const reviewed = reviewWordsList.filter(w => w.review_status && w.review_status !== 'pending').length;
        const remaining = Math.max(0, total - reviewed);

        if (rqProgressBadge) rqProgressBadge.textContent = `${reviewed} of ${total} reviewed`;
        if (tbReviewQueueCount) tbReviewQueueCount.textContent = remaining;
        if (panFuzzyCount) panFuzzyCount.textContent = remaining;
        if (rqListRemaining) rqListRemaining.textContent = `${remaining} remaining`;

        const pct = total > 0 ? Math.round((reviewed / total) * 100) : 100;
        if (rqProgressBarFill) rqProgressBarFill.style.width = `${pct}%`;

        if (total > 0 && reviewed >= total) {
            if (rqActiveCard) rqActiveCard.style.display = 'none';
            if (rqCompletedState) rqCompletedState.style.display = 'block';
        } else {
            if (rqActiveCard) rqActiveCard.style.display = 'block';
            if (rqCompletedState) rqCompletedState.style.display = 'none';
        }

        if (rqWordsList) {
            rqWordsList.innerHTML = '';
            reviewWordsList.forEach((word, idx) => {
                const item = document.createElement('div');
                const isReviewed = word.review_status && word.review_status !== 'pending';
                const isActive = (idx === reviewCurrentIndex);
                item.className = `rq-item ${isReviewed ? 'reviewed' : ''} ${isActive ? 'active' : ''}`;

                let statusIcon = '<span class="rq-item-status-icon pending"><i class="fa-regular fa-circle"></i></span>';
                if (word.review_status === 'accepted') {
                    statusIcon = '<span class="rq-item-status-icon accepted"><i class="fa-solid fa-check"></i></span>';
                } else if (word.review_status === 'edited') {
                    statusIcon = '<span class="rq-item-status-icon accepted"><i class="fa-solid fa-pen"></i></span>';
                } else if (word.review_status === 'skipped') {
                    statusIcon = '<span class="rq-item-status-icon skipped"><i class="fa-solid fa-forward"></i></span>';
                }

                item.innerHTML = `
                    ${statusIcon}
                    <span class="rq-item-text" title="${escapeHtml(word.edited_text || word.text)}">${escapeHtml(word.edited_text || word.text)}</span>
                    <span class="rq-item-conf conf-${word.conf_tier || (word.conf < 60 ? 'low' : 'med')}">${word.conf}%</span>
                `;

                item.addEventListener('click', () => {
                    selectReviewWord(idx);
                });
                rqWordsList.appendChild(item);
            });
            const activeItemEl = rqWordsList.querySelector('.rq-item.active');
            if (activeItemEl) {
                activeItemEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    }

    // Heatmap listeners
    if (tbBtnHeatmap) {
        tbBtnHeatmap.addEventListener('click', (e) => {
            e.preventDefault();
            toggleConfidenceHeatmap();
        });
    }

    if (tbHeatmapSlider) {
        tbHeatmapSlider.addEventListener('input', () => {
            updateHeatmapTiers();
        });
    }

    // Review Queue listeners
    if (tbBtnReviewQueue) {
        tbBtnReviewQueue.addEventListener('click', (e) => {
            e.preventDefault();
            if (isReviewQueueOpen) {
                closeReviewQueue();
            } else {
                openReviewQueue();
            }
        });
    }

    if (panBtnOpenReviewQueue) {
        panBtnOpenReviewQueue.addEventListener('click', (e) => {
            e.preventDefault();
            openReviewQueue();
        });
    }

    if (rqBtnClose) {
        rqBtnClose.addEventListener('click', (e) => {
            e.preventDefault();
            closeReviewQueue();
        });
    }

    if (rqBtnAccept) {
        rqBtnAccept.addEventListener('click', (e) => {
            e.preventDefault();
            acceptCurrentWord();
        });
    }

    if (rqBtnEdit) {
        rqBtnEdit.addEventListener('click', (e) => {
            e.preventDefault();
            focusEditField();
        });
    }

    if (rqBtnSkip) {
        rqBtnSkip.addEventListener('click', (e) => {
            e.preventDefault();
            skipCurrentWord();
        });
    }

    if (rqBtnRestart) {
        rqBtnRestart.addEventListener('click', () => {
            reviewWordsList.forEach(w => {
                w.review_status = 'pending';
            });
            if (reviewWordsList.length > 0) {
                selectReviewWord(0);
            }
            renderReviewQueueUI();
        });
    }

    if (rqWordInput) {
        rqWordInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                acceptCurrentWord();
                rqWordInput.blur();
            }
        });
    }

    // Global keyboard shortcuts (Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y, Ctrl+F, Delete, B hold, Escape, and Review Queue J/K/Enter/E/S)
    window.addEventListener('keydown', (e) => {
        // Review Queue Keyboard Navigation (Next/Prev: J/K or arrows, Accept: Enter, Edit: E, Skip: S)
        if (isReviewQueueOpen) {
            // When user is typing inside the word edit input:
            if (document.activeElement === rqWordInput) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    acceptCurrentWord();
                    rqWordInput.blur();
                    return;
                }
                if (e.key === 'Escape') {
                    e.preventDefault();
                    rqWordInput.blur();
                    return;
                }
                // Allow regular typing
                return;
            }

            // Keyboard navigation while review panel is open:
            if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                if (e.key.toLowerCase() === 'j' || e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (reviewWordsList.length > 0) {
                        const nextIdx = Math.min(reviewWordsList.length - 1, reviewCurrentIndex + 1);
                        selectReviewWord(nextIdx);
                    }
                    return;
                }
                if (e.key.toLowerCase() === 'k' || e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (reviewWordsList.length > 0) {
                        const prevIdx = Math.max(0, reviewCurrentIndex - 1);
                        selectReviewWord(prevIdx);
                    }
                    return;
                }
                if (e.key === 'Enter') {
                    e.preventDefault();
                    acceptCurrentWord();
                    return;
                }
                if (e.key.toLowerCase() === 'e') {
                    e.preventDefault();
                    focusEditField();
                    return;
                }
                if (e.key.toLowerCase() === 's') {
                    e.preventDefault();
                    skipCurrentWord();
                    return;
                }
            }
        }

        const isEditingInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || (e.target.isContentEditable && e.target !== activeBlockEl);

        // Save: Ctrl+S (or Cmd+S)
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            saveDocumentInPlace();
            return;
        }

        // Undo: Ctrl+Z (or Cmd+Z)
        if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            docCommandStack.undo();
            return;
        }

        // Redo: Ctrl+Shift+Z or Ctrl+Y (or Cmd+Shift+Z)
        if ((e.ctrlKey || e.metaKey) && ((e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y')) {
            e.preventDefault();
            docCommandStack.redo();
            return;
        }

        // Find: Ctrl+F or Ctrl+H
        if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'f' || e.key.toLowerCase() === 'h')) {
            e.preventDefault();
            openFindReplacePanel();
            return;
        }

        // Escape: dismiss panels and modes
        if (e.key === 'Escape') {
            if (isAddingBoxMode) cancelAddingBoxMode();
            if (doceditFindReplacePanel && doceditFindReplacePanel.classList.contains('show')) closeFindReplacePanel();
            if (doceditApplyAllModal && doceditApplyAllModal.classList.contains('show')) closeApplyAllModal();
            if (isReviewQueueOpen) {
                closeReviewQueue();
                return;
            }
            return;
        }

        // Delete key on active block (when whole block is selected or focused)
        if (e.key === 'Delete') {
            if (activeBlockEl && activeBlockData && document.activeElement === activeBlockEl) {
                const sel = window.getSelection();
                if (!sel || sel.isCollapsed || sel.toString() === activeBlockEl.innerText) {
                    e.preventDefault();
                    deleteActiveBlock();
                    return;
                }
            }
        }

        // Hold 'B' key for Before/After compare preview
        if (e.key.toLowerCase() === 'b' && !e.ctrlKey && !e.metaKey && !e.altKey && !isHoldingBKey && !isEditingInput) {
            isHoldingBKey = true;
            toggleBeforeAfter(true);
        }
    });

    window.addEventListener('keyup', (e) => {
        if (e.key.toLowerCase() === 'b' && isHoldingBKey) {
            isHoldingBKey = false;
            toggleBeforeAfter(false);
        }
    });
});

