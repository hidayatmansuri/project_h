/**
 * Shades App - project-h
 * Interactive Color Palette:
 * - Generates shades from #000000 to #FFFFFF in ascending order
 * - Two-square layout (top color square, bottom offset value square)
 * - Copy to clipboard with instant micro-interaction and toast notification
 * - Mobile-first responsive filtering, search, and infinite scrolling
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const grid = document.getElementById('shadesGrid');
    const searchInput = document.getElementById('shadesSearch');
    const sortSelect = document.getElementById('shadesSort');
    const tabButtons = document.querySelectorAll('.shades-tab-btn');
    const countBadge = document.getElementById('shadesCountBadge');
    const loadMoreContainer = document.getElementById('loadMoreContainer');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const toast = document.getElementById('shadeToast');
    const toastMsg = document.getElementById('shadeToastMsg');

    // State
    let currentMode = 'grayscale'; // 'grayscale', 'spectrum', 'reds', 'greens', 'blues', 'websafe'
    let fullColorList = [];
    let filteredList = [];
    let renderedCount = 0;
    const CHUNK_SIZE = 60;
    let toastTimeout = null;

    // Helper: Component to Hex
    const toHex = (c) => {
        const h = Math.max(0, Math.min(255, Math.round(c))).toString(16).toUpperCase();
        return h.length === 1 ? '0' + h : h;
    };

    const rgbToHex = (r, g, b) => `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    const rgbStr = (r, g, b) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;

    // Palette Generators
    const generateGrayscale = () => {
        const list = [];
        for (let i = 0; i <= 255; i++) {
            list.push({
                r: i,
                g: i,
                b: i,
                hex: rgbToHex(i, i, i),
                rgb: rgbStr(i, i, i),
                hexVal: (i << 16) | (i << 8) | i,
                lum: i
            });
        }
        return list;
    };

    const generateSpectrum = (step = 16) => {
        const list = [];
        // Shorthand steps: 0, 17, 34 ... 255 (0x00, 0x11, 0x22 ... 0xFF)
        for (let r = 0; r <= 255; r += step) {
            for (let g = 0; g <= 255; g += step) {
                for (let b = 0; b <= 255; b += step) {
                    const rClamp = Math.min(255, r);
                    const gClamp = Math.min(255, g);
                    const bClamp = Math.min(255, b);
                    list.push({
                        r: rClamp,
                        g: gClamp,
                        b: bClamp,
                        hex: rgbToHex(rClamp, gClamp, bClamp),
                        rgb: rgbStr(rClamp, gClamp, bClamp),
                        hexVal: (rClamp << 16) | (gClamp << 8) | bClamp,
                        lum: 0.299 * rClamp + 0.587 * gClamp + 0.114 * bClamp
                    });
                }
            }
        }
        return list;
    };

    const generateHueShades = (hueR, hueG, hueB, steps = 128) => {
        const list = [];
        // From Black #000000 -> Target Hue -> White #FFFFFF in ascending steps
        const half = Math.floor(steps / 2);
        for (let i = 0; i <= half; i++) {
            const factor = i / half;
            const r = factor * hueR;
            const g = factor * hueG;
            const b = factor * hueB;
            list.push({
                r, g, b,
                hex: rgbToHex(r, g, b),
                rgb: rgbStr(r, g, b),
                hexVal: (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b),
                lum: 0.299 * r + 0.587 * g + 0.114 * b
            });
        }
        for (let i = 1; i <= half; i++) {
            const factor = i / half;
            const r = hueR + factor * (255 - hueR);
            const g = hueG + factor * (255 - hueG);
            const b = hueB + factor * (255 - hueB);
            list.push({
                r, g, b,
                hex: rgbToHex(r, g, b),
                rgb: rgbStr(r, g, b),
                hexVal: (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b),
                lum: 0.299 * r + 0.587 * g + 0.114 * b
            });
        }
        return list;
    };

    const generateWebSafe = () => {
        const steps = [0x00, 0x33, 0x66, 0x99, 0xCC, 0xFF];
        const list = [];
        for (const r of steps) {
            for (const g of steps) {
                for (const b of steps) {
                    list.push({
                        r, g, b,
                        hex: rgbToHex(r, g, b),
                        rgb: rgbStr(r, g, b),
                        hexVal: (r << 16) | (g << 8) | b,
                        lum: 0.299 * r + 0.587 * g + 0.114 * b
                    });
                }
            }
        }
        return list;
    };

    // Load list by current Mode
    const loadModeData = (mode) => {
        currentMode = mode;
        if (mode === 'grayscale') {
            fullColorList = generateGrayscale();
        } else if (mode === 'spectrum') {
            fullColorList = generateSpectrum(17); // 4,096 shades from #000000 to #FFFFFF
        } else if (mode === 'reds') {
            fullColorList = generateHueShades(255, 0, 0, 128);
        } else if (mode === 'greens') {
            fullColorList = generateHueShades(0, 255, 0, 128);
        } else if (mode === 'blues') {
            fullColorList = generateHueShades(0, 0, 255, 128);
        } else if (mode === 'websafe') {
            fullColorList = generateWebSafe();
        }
        applyFiltersAndSort();
    };

    // Sorting & Filtering
    const applyFiltersAndSort = () => {
        const query = (searchInput.value || '').trim().toLowerCase();
        const sortType = sortSelect ? sortSelect.value : 'hex_asc';

        // Filter by query (hex or rgb)
        filteredList = fullColorList.filter(item => {
            if (!query) return true;
            const cleanQuery = query.replace('#', '');
            const hexMatch = item.hex.toLowerCase().includes(query) || item.hex.toLowerCase().replace('#', '').includes(cleanQuery);
            const rgbMatch = item.rgb.toLowerCase().includes(query);
            return hexMatch || rgbMatch;
        });

        // Sort
        if (sortType === 'hex_asc') {
            filteredList.sort((a, b) => a.hexVal - b.hexVal);
        } else if (sortType === 'hex_desc') {
            filteredList.sort((a, b) => b.hexVal - a.hexVal);
        } else if (sortType === 'lum_asc') {
            filteredList.sort((a, b) => a.lum - b.lum);
        } else if (sortType === 'lum_desc') {
            filteredList.sort((a, b) => b.lum - a.lum);
        }

        // Reset and render first chunk
        grid.innerHTML = '';
        renderedCount = 0;
        renderNextChunk();
        updateCountBadge();
    };

    // Render chunk of shades
    const renderNextChunk = () => {
        if (!filteredList.length) {
            grid.innerHTML = `
                <div class="shades-empty">
                    <i class="fa-solid fa-eye-slash"></i>
                    <p>No shades matching your search query.</p>
                    <p style="opacity: 0.7; font-size: 0.9rem;">Try searching by hex (e.g. 1a or #FFFFFF) or RGB value.</p>
                </div>
            `;
            if (loadMoreContainer) loadMoreContainer.style.display = 'none';
            return;
        }

        const nextBatch = filteredList.slice(renderedCount, renderedCount + CHUNK_SIZE);
        const fragment = document.createDocumentFragment();

        nextBatch.forEach(shade => {
            const card = document.createElement('div');
            card.className = 'shade-card';

            card.innerHTML = `
                <div class="shade-color-square" style="background-color: ${shade.hex};" title="Click to copy ${shade.hex}"></div>
                <div class="shade-info-square">
                    <div class="shade-value-row" data-copy="${shade.hex}" title="Click to copy ${shade.hex}">
                        <span class="shade-val-text">${shade.hex}</span>
                        <button type="button" class="shade-copy-btn" aria-label="Copy ${shade.hex}">
                            <i class="fa-regular fa-copy"></i>
                        </button>
                    </div>
                    <div class="shade-value-row" data-copy="${shade.rgb}" title="Click to copy ${shade.rgb}">
                        <span class="shade-val-text">${shade.rgb}</span>
                        <button type="button" class="shade-copy-btn" aria-label="Copy ${shade.rgb}">
                            <i class="fa-regular fa-copy"></i>
                        </button>
                    </div>
                </div>
            `;

            fragment.appendChild(card);
        });

        grid.appendChild(fragment);
        renderedCount += nextBatch.length;

        // Manage Load More button visibility
        if (loadMoreContainer) {
            if (renderedCount < filteredList.length) {
                loadMoreContainer.style.display = 'flex';
                loadMoreBtn.innerText = `Load More (${filteredList.length - renderedCount} remaining)`;
            } else {
                loadMoreContainer.style.display = 'none';
            }
        }
    };

    // Update count badge
    const updateCountBadge = () => {
        if (!countBadge) return;
        const total = filteredList.length;
        if (total === 0) {
            countBadge.innerText = '0 shades';
        } else if (renderedCount < total) {
            countBadge.innerText = `Showing ${renderedCount} of ${total} shades`;
        } else {
            countBadge.innerText = `${total} shades (#000000 → #FFFFFF)`;
        }
    };

    // Copy To Clipboard
    const copyToClipboard = async (text, triggerEl) => {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
            }

            // Visual Feedback on trigger element
            if (triggerEl) {
                const copyBtn = triggerEl.classList.contains('shade-copy-btn')
                    ? triggerEl
                    : triggerEl.querySelector('.shade-copy-btn');

                if (copyBtn) {
                    const icon = copyBtn.querySelector('i');
                    if (icon) {
                        copyBtn.classList.add('copied');
                        icon.className = 'fa-solid fa-check';
                        setTimeout(() => {
                            copyBtn.classList.remove('copied');
                            icon.className = 'fa-regular fa-copy';
                        }, 1200);
                    }
                }
            }

            // Show Toast
            showToast(`Copied ${text} to clipboard!`);
        } catch (err) {
            console.error('Failed to copy: ', err);
            showToast(`Could not copy: ${text}`);
        }
    };

    // Show Toast Notification
    const showToast = (message) => {
        if (!toast || !toastMsg) return;
        toastMsg.innerText = message;
        toast.classList.add('show');
        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, 1800);
    };

    // Event Delegation for Copy Clicks
    grid.addEventListener('click', (e) => {
        // 1. Click on color square
        const colorSquare = e.target.closest('.shade-color-square');
        if (colorSquare) {
            const card = colorSquare.closest('.shade-card');
            const hexRow = card ? card.querySelector('.shade-value-row[data-copy^="#"]') : null;
            const hexVal = hexRow ? hexRow.getAttribute('data-copy') : null;
            if (hexVal) {
                copyToClipboard(hexVal, hexRow);
            }
            return;
        }

        // 2. Click on value row or copy button
        const valueRow = e.target.closest('.shade-value-row');
        if (valueRow) {
            const copyVal = valueRow.getAttribute('data-copy');
            if (copyVal) {
                copyToClipboard(copyVal, valueRow);
            }
        }
    });

    // Search Input Event
    let searchDebounce = null;
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            if (searchDebounce) clearTimeout(searchDebounce);
            searchDebounce = setTimeout(() => {
                applyFiltersAndSort();
            }, 180);
        });
    }

    // Sort Select Event
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            applyFiltersAndSort();
        });
    }

    // Tab Buttons
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const mode = btn.getAttribute('data-mode') || 'grayscale';
            loadModeData(mode);
        });
    });

    // Load More Button
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            renderNextChunk();
            updateCountBadge();
        });
    }

    // Optional: Infinite Scroll on near bottom
    window.addEventListener('scroll', () => {
        if (renderedCount >= filteredList.length) return;
        const scrollPosition = window.innerHeight + window.scrollY;
        const bodyHeight = document.body.offsetHeight;
        if (scrollPosition >= bodyHeight - 400) {
            renderNextChunk();
            updateCountBadge();
        }
    }, { passive: true });

    // Expose copy function globally if needed
    window.copyShadeText = copyToClipboard;

    // Initial Load: Grayscale shades (from #000000 to #FFFFFF in ascending order)
    loadModeData('grayscale');
});
