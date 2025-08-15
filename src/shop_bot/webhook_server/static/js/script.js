document.addEventListener('DOMContentLoaded', function () {
    function initializePasswordToggles() {
        const togglePasswordButtons = document.querySelectorAll('.toggle-password');
        togglePasswordButtons.forEach(button => {
            button.addEventListener('click', function () {
                const parent = this.closest('.form-group') || this.closest('.password-wrapper');
                if (!parent) return;

                const passwordInput = parent.querySelector('input');
                if (!passwordInput) return;

                if (passwordInput.type === 'password') {
                    passwordInput.type = 'text';
                    this.textContent = '🙈';
                } else {
                    passwordInput.type = 'password';
                    this.textContent = '👁️';
                }
            });
        });
    }

    function setupBotControlForms() {
        const startForm = document.querySelector('form[action*="start-bot"]');
        const stopForm = document.querySelector('form[action*="stop-bot"]');

        if (startForm) {
            startForm.addEventListener('submit', function () {
                const button = startForm.querySelector('button[type="submit"]');
                if (button) {
                    button.disabled = true;
                    button.textContent = 'Запускаем...';
                }
            });
        }

        if (stopForm) {
            stopForm.addEventListener('submit', function () {
                const button = stopForm.querySelector('button[type="submit"]');
                if (button) {
                    button.disabled = true;
                    button.textContent = 'Останавливаем...';
                }
            });
        }
    }

    function setupConfirmationForms() {
        const confirmationForms = document.querySelectorAll('form[data-confirm]');
        confirmationForms.forEach(form => {
            form.addEventListener('submit', function (event) {
                const message = form.getAttribute('data-confirm');
                if (!confirm(message)) {
                    event.preventDefault();
                }
            });
        });
    }

    function initializeDashboardCharts() {
        const usersChartCanvas = document.getElementById('newUsersChart');
        if (!usersChartCanvas || typeof CHART_DATA === 'undefined') {
            return;
        }

        function prepareChartData(data, label, color) {
            const labels = [];
            const values = [];
            const today = new Date();

            for (let i = 29; i >= 0; i--) {
                const date = new Date(today);
                date.setDate(today.getDate() - i);
                const dateString = date.toISOString().split('T')[0];
                const formattedDate = `${date.getDate().toString().padStart(2, '0')}.${(date.getMonth() + 1).toString().padStart(2, '0')}`;
                labels.push(formattedDate);
                values.push(data[dateString] || 0);
            }

            return {
                labels: labels,
                datasets: [
                    {
                        label: label,
                        data: values,
                        borderColor: color,
                        backgroundColor: color + '33',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                    },
                ],
            };
        }

        function updateChartFontsAndLabels(chart) {
            const isMobile = window.innerWidth <= 768;
            const isVerySmall = window.innerWidth <= 470;
            chart.options.scales.x.ticks.font.size = isMobile ? 10 : 12;
            chart.options.scales.y.ticks.font.size = isMobile ? 10 : 12;
            chart.options.plugins.legend.labels.font.size = isMobile ? 12 : 14;
            chart.options.scales.x.ticks.maxTicksLimit = isMobile ? 8 : 15;
            // Скрываем метки и легенду при ширине <= 470px
            chart.options.scales.x.ticks.display = !isVerySmall;
            chart.options.scales.y.ticks.display = !isVerySmall;
            chart.options.plugins.legend.display = !isVerySmall;
            chart.update();
        }

        const usersCtx = usersChartCanvas.getContext('2d');
        const usersChartData = prepareChartData(
            CHART_DATA.users,
            'Новых пользователей в день',
            '#007bff'
        );
        const usersChart = new Chart(usersCtx, {
            type: 'line',
            data: usersChartData,
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            font: {
                                size: window.innerWidth <= 768 ? 10 : 12
                            },
                            display: window.innerWidth > 470
                        }
                    },
                    x: {
                        ticks: {
                            font: {
                                size: window.innerWidth <= 768 ? 10 : 12
                            },
                            maxTicksLimit: window.innerWidth <= 768 ? 8 : 15,
                            maxRotation: 45,
                            minRotation: 45,
                            display: window.innerWidth > 470
                        }
                    }
                },
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    autoPadding: true,
                    padding: 0
                },
                plugins: {
                    legend: {
                        labels: {
                            font: {
                                size: window.innerWidth <= 768 ? 12 : 14
                            },
                            display: window.innerWidth > 470
                        }
                    }
                }
            }
        });

        const keysChartCanvas = document.getElementById('newKeysChart');
        if (!keysChartCanvas) return;

        const keysCtx = keysChartCanvas.getContext('2d');
        const keysChartData = prepareChartData(
            CHART_DATA.keys,
            'Новых ключей в день',
            '#28a745'
        );
        const keysChart = new Chart(keysCtx, {
            type: 'line',
            data: keysChartData,
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            font: {
                                size: window.innerWidth <= 768 ? 10 : 12
                            },
                            display: window.innerWidth > 470
                        }
                    },
                    x: {
                        ticks: {
                            font: {
                                size: window.innerWidth <= 768 ? 10 : 12
                            },
                            maxTicksLimit: window.innerWidth <= 768 ? 8 : 15,
                            maxRotation: 45,
                            minRotation: 45,
                            display: window.innerWidth > 470
                        }
                    }
                },
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    autoPadding: true,
                    padding: 0
                },
                plugins: {
                    legend: {
                        labels: {
                            font: {
                                size: window.innerWidth <= 768 ? 12 : 14
                            },
                            display: window.innerWidth > 470
                        }
                    }
                }
            }
        });

        window.addEventListener('resize', () => {
            updateChartFontsAndLabels(usersChart);
            updateChartFontsAndLabels(keysChart);
        });
    }

    initializePasswordToggles();
    setupBotControlForms();
    setupConfirmationForms();
    initializeDashboardCharts();
});