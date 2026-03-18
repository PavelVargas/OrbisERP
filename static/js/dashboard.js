/**
 * OrbisERP Dashboard Engine
 * Gestiona la renderización de gráficos y UI dinámica con soporte multimoneda.
 */

const initDashboardChart = () => {
    const canvas = document.getElementById('myChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    
    // 1. Extraer estilos computados de base.css para mantener coherencia visual
    const style = getComputedStyle(document.body);
    
    const primaryColor = style.getPropertyValue('--primary').trim() || '#4f46e5';
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

    // 3. Crear Gradiente basado en el color primario actual
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, primaryColor + '66'); // 40% opacidad
    gradient.addColorStop(1, primaryColor + '00'); // Transparente

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
                pointBackgroundColor: primaryColor,
                pointBorderColor: cardBg,
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                tension: 0.4 
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false 
                },
                tooltip: {
                    backgroundColor: cardBg,
                    titleColor: mainText,
                    bodyColor: mainText,
                    padding: 12,
                    borderColor: primaryColor + '33',
                    borderWidth: 1,
                    displayColors: false,
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
                    ticks: {
                        color: textColor,
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif",
                            size: 11
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: textColor,
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif",
                            size: 11
                        },
                        // ETIQUETA LATERAL: Usa el símbolo de la base de datos
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