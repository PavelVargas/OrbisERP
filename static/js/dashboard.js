/**
 * OrbisERP Dashboard Engine
 * Gestiona la renderización de gráficos y UI dinámica con soporte multimoneda.
 */

const initDashboardChart = () => {
    const canvas = document.getElementById('myChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // 1. Extraer estilos computados de dashboard.css para mantener coherencia visual
    const style = getComputedStyle(document.body);

    const primaryColor = style.getPropertyValue('--accent').trim() || style.getPropertyValue('--primary').trim() || '#faa200';
    const textColor = style.getPropertyValue('--text-muted').trim() || '#94a3b8';
    const gridColor = style.getPropertyValue('--border').trim() || 'rgba(0,0,0,0.1)';
    const cardBg = style.getPropertyValue('--bg-card').trim() || '#ffffff';
    const mainText = style.getPropertyValue('--text-main').trim() || '#1e293b';

    // 2. Recuperar datos y CONFIGURACIÓN DE DIVISA desde data-attributes
    // Estos valores vienen del backend (app.py -> inject_global_data)
    const labels = JSON.parse(canvas.getAttribute('data-labels') || '[]');
    const dataValues = JSON.parse(canvas.getAttribute('data-values') || '[]');
    const currencyISO = canvas.getAttribute('data-currency-iso') || 'DOP';
    const currencySymbol = canvas.getAttribute('data-currency-symbol') || 'RD$';

    // 3. Crear gradiente vertical basado en el color de acento actual
    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, primaryColor + '55'); // ~33% opacidad arriba
    gradient.addColorStop(0.6, primaryColor + '14');
    gradient.addColorStop(1, primaryColor + '00'); // transparente abajo

    // Destruir instancia previa si existe (evita solapamiento al redibujar)
    const existingChart = Chart.getChart("myChart");
    if (existingChart) {
        existingChart.destroy();
    }

    // 4. Configuración de Chart.js
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Ventas Totales',
                data: dataValues,
                fill: true,
                backgroundColor: gradient,
                borderColor: primaryColor,
                borderWidth: 3,
                pointBackgroundColor: cardBg,
                pointBorderColor: primaryColor,
                pointBorderWidth: 2.5,
                pointRadius: 4,
                pointHoverRadius: 7,
                pointHoverBackgroundColor: primaryColor,
                pointHoverBorderColor: cardBg,
                pointHoverBorderWidth: 3,
                cubicInterpolationMode: 'monotone',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 8, right: 4, bottom: 0, left: 0 }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: cardBg,
                    titleColor: mainText,
                    bodyColor: mainText,
                    padding: 14,
                    borderColor: primaryColor + '40',
                    borderWidth: 1,
                    cornerRadius: 14,
                    displayColors: false,
                    titleFont: {
                        family: "'DM Sans', sans-serif",
                        size: 12,
                        weight: '600'
                    },
                    bodyFont: {
                        family: "'DM Mono', monospace",
                        size: 13,
                        weight: '500'
                    },
                    boxPadding: 6,
                    callbacks: {
                        label: function(context) {
                            // FORMATEO DINÁMICO: Fiel a la moneda de la sesión/empresa
                            if (context.parsed.y !== null) {
                                return new Intl.NumberFormat('en-US', {
                                    style: 'currency',
                                    currency: currencyISO
                                }).format(context.parsed.y);
                            }
                            return context.parsed.y;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    border: {
                        display: false
                    },
                    ticks: {
                        color: textColor,
                        font: {
                            family: "'DM Sans', sans-serif",
                            size: 11,
                            weight: '500'
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: gridColor,
                        drawBorder: false,
                        // líneas punteadas: look más limpio que las sólidas en un panel redondeado
                        dash: [4, 5]
                    },
                    border: {
                        display: false
                    },
                    ticks: {
                        color: textColor,
                        font: {
                            family: "'DM Mono', monospace",
                            size: 11
                        },
                        // ETIQUETA LATERAL: usa el símbolo de la base de datos
                        callback: function(value) {
                            return currencySymbol + ' ' + value.toLocaleString();
                        }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index',
            }
        }
    });
};

const observeThemeChange = () => {
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'class' || mutation.attributeName === 'data-theme') {
                // Pequeño delay para dejar que el CSS se aplique antes de leer colores
                setTimeout(() => {
                    initDashboardChart();
                }, 100);
            }
        });
    });
    observer.observe(document.documentElement, { attributes: true });
    observer.observe(document.body, { attributes: true });
};

// Inicialización al cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
    initDashboardChart();
    observeThemeChange();
});