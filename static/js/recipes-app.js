/**
 * Recipes - Interactive UI Script
 * Controls Recipe Square Cards, Full Recipe Modals, and Admin Dynamic Form Rows
 */

(function ($) {
    'use strict';

    $(document).ready(function () {

        // ======================================================================
        // 1. RECIPE MODAL SYSTEM
        // ======================================================================

        // Open modal when clicking or pressing Enter/Space on a square recipe card
        $(document).on('click', '[data-recipe-modal]', function (e) {
            e.preventDefault();
            var modalId = $(this).attr('data-recipe-modal');
            openRecipeModal(modalId);
        });

        $(document).on('keydown', '[data-recipe-modal]', function (e) {
            if (e.key === 'Enter' || e.key === ' ' || e.keyCode === 13 || e.keyCode === 32) {
                e.preventDefault();
                var modalId = $(this).attr('data-recipe-modal');
                openRecipeModal(modalId);
            }
        });

        function openRecipeModal(modalId) {
            var $modal = $('#' + modalId);
            if ($modal.length) {
                // Close any existing open modals first
                $('.recipe-modal.is-open').removeClass('is-open').attr('aria-hidden', 'true');

                $modal.addClass('is-open').attr('aria-hidden', 'false');
                $('body').addClass('modal-open-lock');

                // Focus close button for keyboard accessibility
                var $closeBtn = $modal.find('.recipe-modal-close');
                if ($closeBtn.length) {
                    $closeBtn.focus();
                }
            }
        }

        // Close modal when clicking backdrop or close buttons
        $(document).on('click', '[data-close-modal]', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var $modal = $(this).closest('.recipe-modal');
            closeRecipeModal($modal);
        });

        // Close modal when clicking directly on modal background area
        $(document).on('click', '.recipe-modal', function (e) {
            if (e.target === this) {
                e.preventDefault();
                closeRecipeModal($(this));
            }
        });

        // Close modal when pressing Escape key
        $(document).on('keydown', function (e) {
            if (e.key === 'Escape' || e.keyCode === 27) {
                var $openModal = $('.recipe-modal.is-open');
                if ($openModal.length) {
                    closeRecipeModal($openModal);
                }
            }
        });

        function closeRecipeModal($modal) {
            if (!$modal || !$modal.length) {
                $modal = $('.recipe-modal.is-open');
            }
            $modal.removeClass('is-open').attr('aria-hidden', 'true');
            if ($('.recipe-modal.is-open').length === 0) {
                $('body').removeClass('modal-open-lock');
            }
        }

        // ======================================================================
        // 2. ADMIN DYNAMIC INGREDIENT & METHOD BUILDER
        // ======================================================================

        function reindexDynamicRows($container, labelPrefix) {
            if (typeof $container === 'string') {
                $container = $('#' + $container);
            }
            $container.find('.admin-dynamic-row').each(function (index) {
                $(this).find('label').text(labelPrefix + ' ' + (index + 1));
            });
        }

        // Add Ingredient
        $(document).on('click', '#admin-add-ingredient-btn, .btn-add-ingredient', function (e) {
            e.preventDefault();
            var $container = $(this).closest('.admin-dynamic-section').find('.admin-dynamic-container');
            if (!$container.length) {
                $container = $('#admin-ingredients-container');
            }
            var count = $container.find('.admin-dynamic-row').length + 1;

            var rowHtml = [
                '<div class="admin-dynamic-row">',
                '    <div class="input-field dynamic-input-field">',
                '        <i class="material-icons prefix">ballot</i>',
                '        <input name="ingredient[]" type="text" class="validate" placeholder="e.g. Ingredient item">',
                '        <label class="active">Ingredient ' + count + '</label>',
                '    </div>',
                '    <button type="button" class="btn-remove-dynamic" title="Remove" aria-label="Remove ingredient">',
                '        <i class="material-icons">delete_outline</i>',
                '    </button>',
                '</div>'
            ].join('\n');

            var $newRow = $(rowHtml).hide();
            $container.append($newRow);
            $newRow.slideDown(150, function () {
                $newRow.find('input').focus();
            });
            reindexDynamicRows($container, 'Ingredient');
        });

        // Add Method Step
        $(document).on('click', '#admin-add-method-btn, .btn-add-method', function (e) {
            e.preventDefault();
            var $container = $(this).closest('.admin-dynamic-section').find('.admin-dynamic-container');
            if (!$container.length) {
                $container = $('#admin-methods-container');
            }
            var count = $container.find('.admin-dynamic-row').length + 1;

            var rowHtml = [
                '<div class="admin-dynamic-row">',
                '    <div class="input-field dynamic-input-field">',
                '        <i class="material-icons prefix">restaurant</i>',
                '        <input name="method[]" type="text" class="validate" placeholder="e.g. Next instruction step">',
                '        <label class="active">Step ' + count + '</label>',
                '    </div>',
                '    <button type="button" class="btn-remove-dynamic" title="Remove" aria-label="Remove step">',
                '        <i class="material-icons">delete_outline</i>',
                '    </button>',
                '</div>'
            ].join('\n');

            var $newRow = $(rowHtml).hide();
            $container.append($newRow);
            $newRow.slideDown(150, function () {
                $newRow.find('input').focus();
            });
            reindexDynamicRows($container, 'Step');
        });

        // Remove row
        $(document).on('click', '.btn-remove-dynamic', function (e) {
            e.preventDefault();
            var $row = $(this).closest('.admin-dynamic-row');
            var $container = $row.parent();
            var isMethod = $row.find('input[name="method[]"]').length > 0 || ($container.attr('id') || '').indexOf('method') !== -1;
            var labelPrefix = isMethod ? 'Step' : 'Ingredient';

            if ($container.find('.admin-dynamic-row').length > 1) {
                $row.slideUp(150, function () {
                    $row.remove();
                    reindexDynamicRows($container, labelPrefix);
                });
            } else {
                // If only 1 row left, simply clear its value
                $row.find('input').val('').focus();
            }
        });

        // Open embedded recipe editor collapsible when triggered or via URL hash
        function openEmbeddedEditor($section) {
            if (!$section || !$section.length) return;
            var $collapsible = $section.find('.collapsible').first();
            var $firstLi = $collapsible.children('li').first();
            if ($firstLi.length && !$firstLi.hasClass('active')) {
                $firstLi.children('.collapsible-header').trigger('click');
            }
        }

        $(document).on('click', '.js-open-recipe-editor', function (e) {
            var $editor = $('#embedded-recipe-editor');
            if ($editor.length) {
                e.preventDefault();
                openEmbeddedEditor($editor);
                $('html, body').stop().animate({
                    scrollTop: $editor.offset().top - 80
                }, 400);
            }
        });

        if (window.location.hash === '#embedded-recipe-editor') {
            setTimeout(function () {
                openEmbeddedEditor($('#embedded-recipe-editor'));
            }, 150);
        }

        // ======================================================================
        // 3. LANDING PAGE LIVE SEARCH & FILTERING
        // ======================================================================

        var $searchInput = $('#recipe-search-input');
        var $clearBtn = $('#search-clear-btn');
        var $feedback = $('#search-feedback');

        function performSearch(query) {
            query = (query || '').trim().toLowerCase();

            if (!query) {
                // Reset all
                $('.recipe-card-square').removeClass('is-search-hidden');
                $('.category-card-col').removeClass('is-search-hidden');
                $('.cuisine-card-col').removeClass('is-search-hidden');
                $clearBtn.removeClass('is-active');
                $feedback.removeClass('is-visible').text('');
                return;
            }

            $clearBtn.addClass('is-active');

            var matchCount = 0;

            // Filter recipe square cards
            $('.recipe-card-square').each(function () {
                var name = $(this).attr('data-recipe-name') || '';
                var cat = $(this).attr('data-recipe-category') || '';
                var cus = $(this).attr('data-recipe-cuisine') || '';
                var ing = $(this).attr('data-recipe-ingredients') || '';
                var combined = (name + ' ' + cat + ' ' + cus + ' ' + ing).toLowerCase();

                if (combined.indexOf(query) !== -1) {
                    $(this).removeClass('is-search-hidden');
                    matchCount++;
                } else {
                    $(this).addClass('is-search-hidden');
                }
            });

            // Filter category cards
            $('.category-card-col').each(function () {
                var text = $(this).text().toLowerCase();
                if (text.indexOf(query) !== -1) {
                    $(this).removeClass('is-search-hidden');
                } else {
                    $(this).addClass('is-search-hidden');
                }
            });

            // Filter cuisine cards
            $('.cuisine-card-col').each(function () {
                var text = $(this).text().toLowerCase();
                if (text.indexOf(query) !== -1) {
                    $(this).removeClass('is-search-hidden');
                } else {
                    $(this).addClass('is-search-hidden');
                }
            });

            // Update feedback banner
            if (matchCount > 0) {
                $feedback.addClass('is-visible').html('<i class="fas fa-check-circle"></i> Found ' + matchCount + ' recipe' + (matchCount === 1 ? '' : 's') + ' matching "' + $('<div>').text(query).html() + '"');
            } else {
                $feedback.addClass('is-visible').html('<i class="fas fa-info-circle"></i> No recipes directly match "' + $('<div>').text(query).html() + '". Showing category matches.');
            }
        }

        $searchInput.on('input', function () {
            performSearch($(this).val());
        });

        $clearBtn.on('click', function () {
            $searchInput.val('').focus();
            performSearch('');
        });

        // ======================================================================
        // 4. "SURPRISE ME!" RANDOM RECIPE GENERATOR
        // ======================================================================

        $('#btn-surprise-recipe').on('click', function (e) {
            e.preventDefault();
            var $cards = $('.recipe-card-square:not(.is-search-hidden)');
            if (!$cards.length) {
                $cards = $('.recipe-card-square');
            }
            if (!$cards.length) return;

            var randomIndex = Math.floor(Math.random() * $cards.length);
            var $selectedCard = $cards.eq(randomIndex);
            var modalId = $selectedCard.attr('data-recipe-modal');

            // Visual feedback: scroll to card and flash
            $('html, body').animate({
                scrollTop: $selectedCard.offset().top - 140
            }, 400, function () {
                $selectedCard.addClass('surprise-highlight');
                setTimeout(function () {
                    $selectedCard.removeClass('surprise-highlight');
                    if (modalId) {
                        openRecipeModal(modalId);
                    }
                }, 750);
            });
        });

        // ======================================================================
        // 5. FEATURED SHOWCASE FILTER PILLS
        // ======================================================================

        $('.filter-pill-btn').on('click', function (e) {
            e.preventDefault();
            var filter = $(this).attr('data-filter');
            $('.filter-pill-btn').removeClass('active');
            $(this).addClass('active');

            // Reset search input if user clicks filter
            if ($searchInput.val()) {
                $searchInput.val('');
                $clearBtn.removeClass('is-active');
                $feedback.removeClass('is-visible').text('');
            }

            $('.recipe-card-square').each(function () {
                var $card = $(this);
                var cookTime = parseInt($card.attr('data-cook-time') || '0', 10);
                var category = ($card.attr('data-recipe-category') || '').toLowerCase();
                var cuisine = ($card.attr('data-recipe-cuisine') || '').toLowerCase();

                var show = true;
                if (filter === 'all') {
                    show = true;
                } else if (filter === 'u30') {
                    show = (cookTime > 0 && cookTime <= 30);
                } else if (filter === 'veg') {
                    show = (category.indexOf('veg') !== -1 || category.indexOf('healthy') !== -1);
                } else if (filter === 'meat') {
                    show = (category.indexOf('chick') !== -1 || category.indexOf('beef') !== -1 || category.indexOf('lamb') !== -1 || category.indexOf('pork') !== -1 || category.indexOf('sea food') !== -1 || category.indexOf('seafood') !== -1);
                } else if (filter === 'global') {
                    show = (cuisine.length > 0);
                }

                if (show) {
                    $card.removeClass('is-search-hidden');
                } else {
                    $card.addClass('is-search-hidden');
                }
            });
        });

        // ======================================================================
        // 6. SMOOTH SCROLL FOR BACK-TO-TOP & IN-PAGE ANCHORS
        // ======================================================================

        $('a[href^="#"]').on('click', function (e) {
            var target = $(this.getAttribute('href'));
            if (target.length) {
                e.preventDefault();
                $('html, body').stop().animate({
                    scrollTop: target.offset().top - 80
                }, 400);
            }
        });

    });

})(jQuery);
