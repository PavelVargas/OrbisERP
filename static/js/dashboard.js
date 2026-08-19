/**
 * OrbisERP command center charts.
 * Data is serialized by Jinja in #dashboard-data; no business values live here.
 */
(function () {
    'use strict';

    const payloadNode = document.getElementById('dashboard-data');
    if (!payloadNode) return;

    let data;
    try {
        data = JSON.parse(payloadNode.textContent || '{}');
    } catch (error) {
        console.error('No se pudieron leer los datos del dashboard.', error);
        return;
    }

    const palette = ['#df7419', '#3b6ff5', '#098c68', '#8456e8', '#d89b24', '#d8444d'];
    const paymentNames = {
        CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia',
        CREDIT: 'Crédito', CHECK: 'Cheque', OTHER: 'Otro', OTRO: 'Otro'
    };
    let salesChart;
    let paymentChart;

    const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const money = (value, compact = false) => {
        const amount = Number(value || 0);
        const options = compact && Math.abs(amount) >= 1000
            ? { notation: 'compact', maximumFractionDigits: 1 }
            : { minimumFractionDigits: 0, maximumFractionDigits: 2 };
        return `${data.currencySymbol || 'RD$'} ${new Intl.NumberFormat('es-DO', options).format(amount)}`;
    };

    function renderLegend() {
        const legend = document.getElementById('paymentLegend');
        if (!legend) return;
        if (!data.paymentLabels?.length) {
            legend.innerHTML = '<div class="empty-state empty-state--small"><i class="bi bi-wallet2"></i><strong>Sin cobros este mes</strong></div>';
            return;
        }
        legend.replaceChildren(...data.paymentLabels.map((label, index) => {
            const row = document.createElement('span');
            const swatch = document.createElement('i');
            const name = document.createElement('span');
            const value = document.createElement('b');
            swatch.style.backgroundColor = palette[index % palette.length];
            name.textContent = paymentNames[String(label).toUpperCase()] || label;
            value.textContent = money(data.paymentValues[index]);
            row.append(swatch, name, value);
            return row;
        }));
    }

    function renderCharts() {
        renderLegend();
        if (typeof window.Chart === 'undefined') return;

        const muted = css('--hub-muted', '#6f7d78');
        const line = css('--hub-border', '#dfe5e1');
        const surface = css('--hub-card', '#ffffff');
        const ink = css('--hub-text', '#1b2421');
        const accent = css('--hub-orange', '#df7419');
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        const salesCanvas = document.getElementById('salesChart');
        if (salesCanvas) {
            salesChart?.destroy();
            const context = salesCanvas.getContext('2d');
            const gradient = context.createLinearGradient(0, 0, 0, 255);
            gradient.addColorStop(0, 'rgba(223, 116, 25, .20)');
            gradient.addColorStop(.6, 'rgba(223, 116, 25, .05)');
            gradient.addColorStop(1, 'rgba(223, 116, 25, 0)');
            const labelStep = data.period >= 90 ? 14 : data.period >= 30 ? 5 : 1;

            salesChart = new Chart(context, {
                type: 'line',
                data: {
                    labels: data.labels || [],
                    datasets: [{
                        data: data.sales || [],
                        borderColor: accent,
                        backgroundColor: gradient,
                        borderWidth: 2.5,
                        fill: true,
                        tension: .42,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointHoverBackgroundColor: accent,
                        pointHoverBorderColor: '#ffffff',
                        pointHoverBorderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: reducedMotion ? false : { duration: 650, easing: 'easeOutQuart' },
                    interaction: { intersect: false, mode: 'index' },
                    layout: { padding: { top: 10, right: 7, left: 2 } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            displayColors: false,
                            backgroundColor: surface,
                            titleColor: muted,
                            bodyColor: ink,
                            borderColor: line,
                            borderWidth: 1,
                            padding: 12,
                            cornerRadius: 11,
                            callbacks: { label: context => money(context.parsed.y) }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            border: { display: false },
                            ticks: {
                                color: muted,
                                font: { size: 9, weight: '600' },
                                callback(value, index) { return index % labelStep === 0 || index === data.labels.length - 1 ? this.getLabelForValue(value) : ''; }
                            }
                        },
                        y: {
                            beginAtZero: true,
                            border: { display: false },
                            grid: { color: line, drawTicks: false },
                            ticks: { color: muted, padding: 9, font: { size: 9 }, callback: value => money(value, true) }
                        }
                    }
                }
            });
        }

        const paymentCanvas = document.getElementById('paymentChart');
        if (paymentCanvas && data.paymentLabels?.length) {
            paymentChart?.destroy();
            paymentChart = new Chart(paymentCanvas, {
                type: 'doughnut',
                data: {
                    labels: data.paymentLabels.map(label => paymentNames[String(label).toUpperCase()] || label),
                    datasets: [{ data: data.paymentValues, backgroundColor: palette, borderColor: surface, borderWidth: 3, hoverOffset: 3 }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '74%',
                    animation: reducedMotion ? false : { duration: 700, easing: 'easeOutQuart' },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: surface,
                            titleColor: muted,
                            bodyColor: ink,
                            borderColor: line,
                            borderWidth: 1,
                            displayColors: false,
                            padding: 11,
                            callbacks: { label: context => money(context.parsed) }
                        }
                    }
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', renderCharts);
    window.addEventListener('load', () => {
        if (!salesChart && window.Chart) renderCharts();
    });

    let themeTimer;
    const observer = new MutationObserver(() => {
        clearTimeout(themeTimer);
        themeTimer = setTimeout(renderCharts, 120);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
})();
