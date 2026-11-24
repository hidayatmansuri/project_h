/**
 * Recipes - Interactive UI Script (Vanilla JS, zero jQuery/Materialize dependencies)
 * Controls Collapsible Accordions, Recipe Square Cards, Full Recipe Modals,
 * Admin Dynamic Form Rows, Live Search, Surprise Picker, and Filter Pills.
 */

(function () {
    'use strict';

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function smoothScrollTo(el, offset) {
        if (!el) return;
        var rect = el.getBoundingClientRect();
        var top = window.pageYOffset + rect.top - (offset || 80);
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }

    document.addEventListener('DOMContentLoaded', function () {

        // ======================================================================
        // 0. NATIVE COLLAPSIBLE ACCORDION (replaces Materialize .collapsible())
        // ======================================================================

        function toggleCollapsibleItem(li, forceOpen) {
            if (!li) return;
            var header = li.querySelector(':scope > .collapsible-header');
            var body = li.querySelector(':scope > .collapsible-body');
            if (!body) return;

            var willOpen = typeof forceOpen === 'boolean' ? forceOpen : !li.classList.contains('active');

            // Accordion behavior: close sibling items in the same .collapsible list
            var parentList = li.parentElement;
            if (willOpen && parentList && parentList.classList.contains('collapsible')) {
                Array.prototype.forEach.call(parentList.children, function (sibling) {
                    if (sibling !== li && sibling.classList.contains('active')) {
                        sibling.classList.remove('active');
                        var sibHeader = sibling.querySelector(':scope > .collapsible-header');
                        if (sibHeader) sibHeader.setAttribute('aria-expanded', 'false');
                    }
                });
            }

            li.classList.toggle('active', willOpen);
            if (header) {
                header.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            }
        }

        document.querySelectorAll('.collapsible > li > .collapsible-header').forEach(function (header) {
            header.setAttribute('role', 'button');
            header.setAttribute('tabindex', '0');
            var li = header.parentElement;
            header.setAttribute('aria-expanded', li && li.classList.contains('active') ? 'true' : 'false');
        });

        document.addEventListener('click', function (e) {
            var header = e.target.closest('.collapsible-header');
            if (!header) return;
            var li = header.parentElement;
            if (li && li.parentElement && li.parentElement.classList.contains('collapsible')) {
                e.preventDefault();
                toggleCollapsibleItem(li);
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            var header = e.target.closest('.collapsible-header');
            if (!header) return;
            var li = header.parentElement;
            if (li && li.parentElement && li.parentElement.classList.contains('collapsible')) {
                e.preventDefault();
                toggleCollapsibleItem(li);
            }
        });

        // ======================================================================
        // 1. RECIPE MODAL SYSTEM
        // ======================================================================

        function openRecipeModal(modalId) {
            var modal = document.getElementById(modalId);
            if (!modal) return;

            document.querySelectorAll('.recipe-modal.is-open').forEach(function (m) {
                m.classList.remove('is-open');
                m.setAttribute('aria-hidden', 'true');
            });

            modal.classList.add('is-open');
            modal.setAttribute('aria-hidden', 'false');
            document.body.classList.add('modal-open-lock');

            var closeBtn = modal.querySelector('.recipe-modal-close');
            if (closeBtn) closeBtn.focus();
        }

        function closeRecipeModal(modal) {
            var targets = modal ? [modal] : Array.prototype.slice.call(document.querySelectorAll('.recipe-modal.is-open'));
            targets.forEach(function (m) {
                m.classList.remove('is-open');
                m.setAttribute('aria-hidden', 'true');
            });
            if (document.querySelectorAll('.recipe-modal.is-open').length === 0) {
                document.body.classList.remove('modal-open-lock');
            }
        }

        document.addEventListener('click', function (e) {
            var trigger = e.target.closest('[data-recipe-modal]');
            if (trigger) {
                e.preventDefault();
                openRecipeModal(trigger.getAttribute('data-recipe-modal'));
                return;
            }

            var closeTrigger = e.target.closest('[data-close-modal]');
            if (closeTrigger) {
                e.preventDefault();
                e.stopPropagation();
                closeRecipeModal(closeTrigger.closest('.recipe-modal'));
                return;
            }

            if (e.target.classList && e.target.classList.contains('recipe-modal')) {
                e.preventDefault();
                closeRecipeModal(e.target);
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                var openModals = document.querySelectorAll('.recipe-modal.is-open');
                if (openModals.length) closeRecipeModal(null);
                return;
            }
            if (e.key === 'Enter' || e.key === ' ') {
                var trigger = e.target.closest('[data-recipe-modal]');
                if (trigger) {
                    e.preventDefault();
                    openRecipeModal(trigger.getAttribute('data-recipe-modal'));
                }
            }
        });

        // ======================================================================
        // 2. ADMIN DYNAMIC INGREDIENT & METHOD BUILDER
        // ======================================================================

        function reindexDynamicRows(container, labelPrefix) {
            if (typeof container === 'string') {
                container = document.getElementById(container);
            }
            if (!container) return;
            container.querySelectorAll('.admin-dynamic-row').forEach(function (row, index) {
                var label = row.querySelector('label');
                if (label) label.textContent = labelPrefix + ' ' + (index + 1);
            });
        }

        function appendDynamicRow(container, inputName, iconName, placeholder, labelPrefix) {
            if (!container) return;
            var count = container.querySelectorAll('.admin-dynamic-row').length + 1;
            var wrapper = document.createElement('div');
            wrapper.className = 'admin-dynamic-row';
            wrapper.innerHTML = [
                '    <div class="input-field dynamic-input-field">',
                '        <i class="material-icons prefix">' + iconName + '</i>',
                '        <input name="' + inputName + '" type="text" class="validate" placeholder="' + placeholder + '">',
                '        <label class="active">' + labelPrefix + ' ' + count + '</label>',
                '    </div>',
                '    <button type="button" class="btn-remove-dynamic" title="Remove" aria-label="Remove ' + labelPrefix.toLowerCase() + '">',
                '        <i class="material-icons">delete_outline</i>',
                '    </button>'
            ].join('\n');

            container.appendChild(wrapper);
            reindexDynamicRows(container, labelPrefix);
            var input = wrapper.querySelector('input');
            if (input) input.focus();
        }

        document.addEventListener('click', function (e) {
            var addIngBtn = e.target.closest('#admin-add-ingredient-btn, .btn-add-ingredient');
            if (addIngBtn) {
                e.preventDefault();
                var section = addIngBtn.closest('.admin-dynamic-section');
                var container = (section && section.querySelector('.admin-dynamic-container'))
                    || document.getElementById('admin-ingredients-container');
                appendDynamicRow(container, 'ingredient[]', 'ballot', 'e.g. Ingredient item', 'Ingredient');
                return;
            }

            var addMethodBtn = e.target.closest('#admin-add-method-btn, .btn-add-method');
            if (addMethodBtn) {
                e.preventDefault();
                var mSection = addMethodBtn.closest('.admin-dynamic-section');
                var mContainer = (mSection && mSection.querySelector('.admin-dynamic-container'))
                    || document.getElementById('admin-methods-container');
                appendDynamicRow(mContainer, 'method[]', 'restaurant', 'e.g. Next instruction step', 'Step');
                return;
            }

            var removeBtn = e.target.closest('.btn-remove-dynamic');
            if (removeBtn) {
                e.preventDefault();
                var row = removeBtn.closest('.admin-dynamic-row');
                if (!row) return;
                var parent = row.parentElement;
                var isMethod = !!row.querySelector('input[name="method[]"]')
                    || ((parent && parent.id) || '').indexOf('method') !== -1;
                var labelPrefix = isMethod ? 'Step' : 'Ingredient';

                if (parent && parent.querySelectorAll('.admin-dynamic-row').length > 1) {
                    row.remove();
                    reindexDynamicRows(parent, labelPrefix);
                } else {
                    var input = row.querySelector('input');
                    if (input) {
                        input.value = '';
                        input.focus();
                    }
                }
            }
        });

        // Open embedded recipe editor collapsible when triggered or via URL hash
        function openEmbeddedEditor(section) {
            if (!section) return;
            var firstLi = section.querySelector('.collapsible > li');
            if (firstLi && !firstLi.classList.contains('active')) {
                toggleCollapsibleItem(firstLi, true);
            }
        }

        document.addEventListener('click', function (e) {
            var openBtn = e.target.closest('.js-open-recipe-editor');
            if (!openBtn) return;
            var editor = document.getElementById('embedded-recipe-editor');
            if (editor) {
                e.preventDefault();
                openEmbeddedEditor(editor);
                smoothScrollTo(editor, 80);
            }
        });

        if (window.location.hash === '#embedded-recipe-editor') {
            setTimeout(function () {
                openEmbeddedEditor(document.getElementById('embedded-recipe-editor'));
            }, 150);
        }

        // ======================================================================
        // 3. LANDING PAGE LIVE SEARCH & FILTERING
        // ======================================================================

        var searchInput = document.getElementById('recipe-search-input');
        var clearBtn = document.getElementById('search-clear-btn');
        var feedback = document.getElementById('search-feedback');

        function performSearch(query) {
            query = (query || '').trim().toLowerCase();
            var cards = document.querySelectorAll('.recipe-card-square');
            var catCols = document.querySelectorAll('.category-card-col');
            var cusCols = document.querySelectorAll('.cuisine-card-col');

            if (!query) {
                cards.forEach(function (el) { el.classList.remove('is-search-hidden'); });
                catCols.forEach(function (el) { el.classList.remove('is-search-hidden'); });
                cusCols.forEach(function (el) { el.classList.remove('is-search-hidden'); });
                if (clearBtn) clearBtn.classList.remove('is-active');
                if (feedback) {
                    feedback.classList.remove('is-visible');
                    feedback.textContent = '';
                }
                return;
            }

            if (clearBtn) clearBtn.classList.add('is-active');

            var matchCount = 0;

            cards.forEach(function (card) {
                var name = card.getAttribute('data-recipe-name') || '';
                var cat = card.getAttribute('data-recipe-category') || '';
                var cus = card.getAttribute('data-recipe-cuisine') || '';
                var ing = card.getAttribute('data-recipe-ingredients') || '';
                var combined = (name + ' ' + cat + ' ' + cus + ' ' + ing).toLowerCase();

                if (combined.indexOf(query) !== -1) {
                    card.classList.remove('is-search-hidden');
                    matchCount++;
                } else {
                    card.classList.add('is-search-hidden');
                }
            });

            catCols.forEach(function (el) {
                el.classList.toggle('is-search-hidden', el.textContent.toLowerCase().indexOf(query) === -1);
            });

            cusCols.forEach(function (el) {
                el.classList.toggle('is-search-hidden', el.textContent.toLowerCase().indexOf(query) === -1);
            });

            if (feedback) {
                feedback.classList.add('is-visible');
                if (matchCount > 0) {
                    feedback.innerHTML = '<i class="fas fa-check-circle"></i> Found ' + matchCount + ' recipe' + (matchCount === 1 ? '' : 's') + ' matching "' + escapeHtml(query) + '"';
                } else {
                    feedback.innerHTML = '<i class="fas fa-info-circle"></i> No recipes directly match "' + escapeHtml(query) + '". Showing category matches.';
                }
            }
        }

        if (searchInput) {
            searchInput.addEventListener('input', function () {
                performSearch(searchInput.value);
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                if (searchInput) {
                    searchInput.value = '';
                    searchInput.focus();
                }
                performSearch('');
            });
        }

        // ======================================================================
        // 4. "SURPRISE ME!" RANDOM RECIPE GENERATOR
        // ======================================================================

        var surpriseBtn = document.getElementById('btn-surprise-recipe');
        if (surpriseBtn) {
            surpriseBtn.addEventListener('click', function (e) {
                e.preventDefault();
                var cards = document.querySelectorAll('.recipe-card-square:not(.is-search-hidden)');
                if (!cards.length) {
                    cards = document.querySelectorAll('.recipe-card-square');
                }
                if (!cards.length) return;

                var selectedCard = cards[Math.floor(Math.random() * cards.length)];
                var modalId = selectedCard.getAttribute('data-recipe-modal');

                smoothScrollTo(selectedCard, 140);
                setTimeout(function () {
                    selectedCard.classList.add('surprise-highlight');
                    setTimeout(function () {
                        selectedCard.classList.remove('surprise-highlight');
                        if (modalId) openRecipeModal(modalId);
                    }, 750);
                }, 400);
            });
        }

        // ======================================================================
        // 5. FEATURED SHOWCASE FILTER PILLS
        // ======================================================================

        document.querySelectorAll('.filter-pill-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                var filter = btn.getAttribute('data-filter');
                document.querySelectorAll('.filter-pill-btn').forEach(function (b) {
                    b.classList.remove('active');
                });
                btn.classList.add('active');

                if (searchInput && searchInput.value) {
                    searchInput.value = '';
                    if (clearBtn) clearBtn.classList.remove('is-active');
                    if (feedback) {
                        feedback.classList.remove('is-visible');
                        feedback.textContent = '';
                    }
                }

                document.querySelectorAll('.recipe-card-square').forEach(function (card) {
                    var cookTime = parseInt(card.getAttribute('data-cook-time') || '0', 10);
                    var category = (card.getAttribute('data-recipe-category') || '').toLowerCase();
                    var cuisine = (card.getAttribute('data-recipe-cuisine') || '').toLowerCase();

                    var show = true;
                    if (filter === 'u30') {
                        show = (cookTime > 0 && cookTime <= 30);
                    } else if (filter === 'veg') {
                        show = (category.indexOf('veg') !== -1 || category.indexOf('healthy') !== -1);
                    } else if (filter === 'meat') {
                        show = (category.indexOf('chick') !== -1 || category.indexOf('beef') !== -1
                            || category.indexOf('lamb') !== -1 || category.indexOf('pork') !== -1
                            || category.indexOf('sea food') !== -1 || category.indexOf('seafood') !== -1);
                    } else if (filter === 'global') {
                        show = (cuisine.length > 0);
                    }

                    card.classList.toggle('is-search-hidden', !show);
                });
            });
        });

        // ======================================================================
        // 6. SMOOTH SCROLL FOR BACK-TO-TOP & IN-PAGE ANCHORS
        // ======================================================================

        document.querySelectorAll('a[href^="#"]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                var href = link.getAttribute('href');
                if (!href || href.length < 2) return;
                var target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    smoothScrollTo(target, 80);
                }
            });
        });

    });
})();
