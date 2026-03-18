(function() {
    'use strict';
    
    // ==============================
    // THEME INITIALIZATION
    // ==============================
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.classList.add('dark');
    }
    
    document.addEventListener('DOMContentLoaded', function() {
        const sidebar = document.getElementById('app-sidebar');
        const toggleBtn = document.getElementById('sidebar-toggle');
        const collapseBtn = document.getElementById('collapse-toggle');
        const overlay = document.getElementById('sidebar-overlay');
        const themeSwitch = document.getElementById('theme-switch');
        
        // ==============================
        // RESTORE COLLAPSED STATE
        // ==============================
        if (localStorage.getItem('sidebar-collapsed') === 'true' && window.innerWidth > 1024) {
            sidebar.classList.add('collapsed');
        }
        
        // ==============================
        // DESKTOP COLLAPSE TOGGLE
        // ==============================
        if (collapseBtn) {
            collapseBtn.addEventListener('click', function() {
                const isCollapsed = sidebar.classList.toggle('collapsed');
                localStorage.setItem('sidebar-collapsed', isCollapsed);
                
                // Trigger resize for charts
                setTimeout(() => {
                    window.dispatchEvent(new Event('resize'));
                }, 300);
            });
        }
        
        // ==============================
        // MOBILE SIDEBAR TOGGLE
        // ==============================
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function() {
                sidebar.classList.toggle('mobile-open');
                overlay.classList.toggle('active');
            });
        }
        
        // ==============================
        // OVERLAY CLICK CLOSE
        // ==============================
        if (overlay) {
            overlay.addEventListener('click', function() {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('active');
            });
        }
        
        // ==============================
        // THEME TOGGLE (CORREGIDO)
        // ==============================
        if (themeSwitch) {
            themeSwitch.addEventListener('click', function() {
                const isDark = document.documentElement.classList.toggle('dark');
                localStorage.setItem('theme', isDark ? 'dark' : 'light');
            });
        }
        
        // ==============================
        // CLOSE MOBILE ON NAV CLICK
        // ==============================
        if (sidebar) {
            const navLinks = sidebar.querySelectorAll('.nav-item');
            navLinks.forEach(link => {
                link.addEventListener('click', function() {
                    if (window.innerWidth <= 1024) {
                        sidebar.classList.remove('mobile-open');
                        overlay.classList.remove('active');
                    }
                });
            });
        }
        
        // ==============================
        // ESC KEY CLOSE
        // ==============================
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('active');
            }
        });
        
        // ==============================
        // HANDLE RESIZE
        // ==============================
        let resizeTimer;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {
                if (window.innerWidth > 1024) {
                    sidebar.classList.remove('mobile-open');
                    overlay.classList.remove('active');
                    
                    if (localStorage.getItem('sidebar-collapsed') === 'true') {
                        sidebar.classList.add('collapsed');
                    }
                } else {
                    sidebar.classList.remove('collapsed');
                }
            }, 100);
        });
    });
})();