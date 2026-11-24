/**
 * CV Interactive Charts & Skill Filtering — project-h
 * Reuses Chart.js + project-h CSS theme variables with Gotu typography
 * and automatic Light/Dark mode color synchronization.
 */
(function () {
    'use strict';

    function getThemeColors() {
        var styles = getComputedStyle(document.documentElement);
        var textColor = styles.getPropertyValue('--text-color').trim() || '#212A31';
        var buttonColor = styles.getPropertyValue('--button-color').trim() || '#42243C';
        var warningColor = styles.getPropertyValue('--warning-color').trim() || '#D94E00';
        var hoverColor = styles.getPropertyValue('--hover-color').trim() || '#800000';
        var isDark = document.documentElement.classList.contains('dark');
        var gridColor = isDark ? 'rgba(211, 217, 212, 0.16)' : 'rgba(33, 42, 49, 0.14)';
        var fillAlpha = isDark ? 'rgba(0, 210, 211, 0.22)' : 'rgba(66, 36, 60, 0.18)';

        return {
            textColor: textColor,
            buttonColor: buttonColor,
            warningColor: warningColor,
            hoverColor: hoverColor,
            gridColor: gridColor,
            fillAlpha: fillAlpha,
        };
    }

    document.addEventListener('DOMContentLoaded', function () {
        var dataEl = document.getElementById('cv-chart-data');
        if (!dataEl) return;

        var payload = {};
        try {
            payload = JSON.parse(dataEl.textContent || '{}');
        } catch (e) {
            return;
        }

        var skills = payload.skills || [];
        var charts = [];

        if (typeof Chart !== 'undefined') {
            Chart.defaults.font.family = 'Gotu, sans-serif';
        }

        var colors = getThemeColors();

        // 1. Competency Radar Chart
        var radarCanvas = document.getElementById('cvRadarChart');
        var radarChart = null;
        if (radarCanvas && typeof Chart !== 'undefined' && (payload.radar_labels || []).length > 0) {
            radarChart = new Chart(radarCanvas.getContext('2d'), {
                type: 'radar',
                data: {
                    labels: payload.radar_labels,
                    datasets: [{
                        label: 'Domain Proficiency (%)',
                        data: payload.radar_values,
                        borderColor: colors.buttonColor,
                        backgroundColor: colors.fillAlpha,
                        pointBackgroundColor: colors.warningColor,
                        pointBorderColor: colors.buttonColor,
                        borderWidth: 2,
                        pointRadius: 4,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            min: 0,
                            max: 100,
                            ticks: {
                                stepSize: 25,
                                color: colors.textColor,
                                backdropColor: 'transparent',
                                font: { family: 'Gotu', size: 11 },
                            },
                            grid: { color: colors.gridColor },
                            angleLines: { color: colors.gridColor },
                            pointLabels: {
                                color: colors.textColor,
                                font: { family: 'Gotu', size: 12, weight: '600' },
                            },
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            titleFont: { family: 'Gotu', size: 13 },
                            bodyFont: { family: 'Gotu', size: 12 },
                        }
                    }
                }
            });
            charts.push(radarChart);
        }

        // 2. Skills Proficiency Horizontal Bar Chart
        var skillsCanvas = document.getElementById('cvSkillsChart');
        var skillsChart = null;
        if (skillsCanvas && typeof Chart !== 'undefined' && skills.length > 0) {
            skillsChart = new Chart(skillsCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: skills.map(function (s) { return s.name; }),
                    datasets: [{
                        label: 'Proficiency (%)',
                        data: skills.map(function (s) { return s.score; }),
                        backgroundColor: colors.buttonColor,
                        hoverBackgroundColor: colors.warningColor,
                        borderRadius: 6,
                        maxBarThickness: 22,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            min: 0,
                            max: 100,
                            ticks: {
                                color: colors.textColor,
                                font: { family: 'Gotu', size: 11 },
                                callback: function (v) { return v + '%'; }
                            },
                            grid: { color: colors.gridColor }
                        },
                        y: {
                            ticks: {
                                color: colors.textColor,
                                font: { family: 'Gotu', size: 11 }
                            },
                            grid: { display: false }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            titleFont: { family: 'Gotu', size: 13 },
                            bodyFont: { family: 'Gotu', size: 12 },
                            callbacks: {
                                label: function (ctx) {
                                    return ' ' + ctx.parsed.x + '%';
                                }
                            }
                        }
                    }
                }
            });
            charts.push(skillsChart);
        }

        // 3. Experience Duration / Industry Breakdown Chart (when DB experiences exist)
        var expCanvas = document.getElementById('cvExperienceChart');
        var expChart = null;
        if (expCanvas && typeof Chart !== 'undefined' && (payload.timeline_labels || []).length > 0) {
            expChart = new Chart(expCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: payload.timeline_labels,
                    datasets: [{
                        label: 'Duration (Years)',
                        data: payload.timeline_years,
                        backgroundColor: colors.warningColor,
                        hoverBackgroundColor: colors.buttonColor,
                        borderRadius: 6,
                        maxBarThickness: 28,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: colors.textColor,
                                font: { family: 'Gotu', size: 11 },
                                callback: function (v) { return v + ' yr'; }
                            },
                            grid: { color: colors.gridColor }
                        },
                        x: {
                            ticks: {
                                color: colors.textColor,
                                font: { family: 'Gotu', size: 11 }
                            },
                            grid: { display: false }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            titleFont: { family: 'Gotu', size: 13 },
                            bodyFont: { family: 'Gotu', size: 12 },
                        }
                    }
                }
            });
            charts.push(expChart);
        }

        // Interactive Skill Category Filtering (filters both cards & bar chart)
        var filterButtons = document.querySelectorAll('.cv-filter-btn');
        var skillCards = document.querySelectorAll('.cv-skill-item');

        filterButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var selected = btn.getAttribute('data-category');
                filterButtons.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');

                skillCards.forEach(function (card) {
                    var cat = card.getAttribute('data-category');
                    var visible = selected === 'all' || cat === selected;
                    card.classList.toggle('is-hidden', !visible);
                });

                if (skillsChart) {
                    var filtered = selected === 'all'
                        ? skills
                        : skills.filter(function (s) { return s.category === selected; });
                    skillsChart.data.labels = filtered.map(function (s) { return s.name; });
                    skillsChart.data.datasets[0].data = filtered.map(function (s) { return s.score; });
                    skillsChart.update();
                }
            });
        });

        // Live sync chart colors when user toggles Light / Dark theme
        function applyThemeToCharts() {
            var c = getThemeColors();
            if (radarChart) {
                radarChart.data.datasets[0].borderColor = c.buttonColor;
                radarChart.data.datasets[0].backgroundColor = c.fillAlpha;
                radarChart.data.datasets[0].pointBackgroundColor = c.warningColor;
                radarChart.data.datasets[0].pointBorderColor = c.buttonColor;
                radarChart.options.scales.r.ticks.color = c.textColor;
                radarChart.options.scales.r.grid.color = c.gridColor;
                radarChart.options.scales.r.angleLines.color = c.gridColor;
                radarChart.options.scales.r.pointLabels.color = c.textColor;
                radarChart.update();
            }
            if (skillsChart) {
                skillsChart.data.datasets[0].backgroundColor = c.buttonColor;
                skillsChart.data.datasets[0].hoverBackgroundColor = c.warningColor;
                skillsChart.options.scales.x.ticks.color = c.textColor;
                skillsChart.options.scales.x.grid.color = c.gridColor;
                skillsChart.options.scales.y.ticks.color = c.textColor;
                skillsChart.update();
            }
            if (expChart) {
                expChart.data.datasets[0].backgroundColor = c.warningColor;
                expChart.data.datasets[0].hoverBackgroundColor = c.buttonColor;
                expChart.options.scales.y.ticks.color = c.textColor;
                expChart.options.scales.y.grid.color = c.gridColor;
                expChart.options.scales.x.ticks.color = c.textColor;
                expChart.update();
            }
        }

        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].attributeName === 'class') {
                    applyThemeToCharts();
                    break;
                }
            }
        });
        observer.observe(document.documentElement, { attributes: true });
    });
})();
