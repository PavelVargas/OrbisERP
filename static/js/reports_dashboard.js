(function () {
    'use strict';
    const source = document.getElementById('reports-data');
    const canvas = document.getElementById('mainChart');
    if (!source || !canvas) return;

    let data;
    try { data = JSON.parse(source.textContent || '{}'); }
    catch (error) { console.error('No se pudieron cargar los datos del informe.', error); return; }

    let chart;
    const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const money = value => `${data.currencySymbol || 'RD$'} ${new Intl.NumberFormat('es-DO', { maximumFractionDigits: 0 }).format(Number(value || 0))}`;

    function draw() {
        if (typeof window.Chart === 'undefined') return;
        chart?.destroy();
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 280);
        gradient.addColorStop(0, 'rgba(223,116,25,.20)');
        gradient.addColorStop(.65, 'rgba(223,116,25,.05)');
        gradient.addColorStop(1, 'rgba(223,116,25,0)');
        const muted = css('--rp-muted', '#71807a');
        const border = css('--rp-border', '#dfe5e1');
        const surface = css('--rp-card', '#fff');
        const text = css('--rp-text', '#1b2421');
        const accent = css('--rp-orange', '#df7419');
        chart = new Chart(ctx, {
            type: 'line',
            data: { labels: data.labels || [], datasets: [{ data: data.values || [], borderColor: accent, backgroundColor: gradient, borderWidth: 2.5, fill: true, tension: .38, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: surface, pointBorderColor: accent, pointBorderWidth: 2 }] },
            options: {
                responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' },
                animation: matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 600, easing: 'easeOutQuart' },
                plugins: { legend: { display: false }, tooltip: { displayColors: false, backgroundColor: surface, titleColor: muted, bodyColor: text, borderColor: border, borderWidth: 1, padding: 11, callbacks: { label: context => money(context.parsed.y) } } },
                scales: {
                    x: { grid: { display: false }, border: { display: false }, ticks: { color: muted, font: { size: 9, weight: '600' } } },
                    y: { beginAtZero: true, grid: { color: border, drawTicks: false }, border: { display: false }, ticks: { color: muted, padding: 9, font: { size: 9 }, callback: money } }
                }
            }
        });
    }

    document.addEventListener('DOMContentLoaded', draw);
    window.addEventListener('load', () => { if (!chart && window.Chart) draw(); });
    let timer;
    new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(draw, 120); }).observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
})();
