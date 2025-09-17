// app/static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    
    const NOTIFICATION_HISTORY_KEY = 'notificationHistory';
    const MAX_HISTORY_ITEMS = 20;
    const notificationHistoryBody = document.getElementById('notification-history-body');

    /**
     * Загружает сохраненную историю уведомлений из localStorage.
     */
    function loadHistoryFromStorage() {
        if (!notificationHistoryBody) return;
        const history = JSON.parse(localStorage.getItem(NOTIFICATION_HISTORY_KEY) || '[]');
        notificationHistoryBody.innerHTML = '';
        history.forEach(item => addNotificationToHistory(item.message, item.type, item.url, false));
    }

    /**
     * Добавляет запись в панель "История уведомлений".
     * @param {string} message - Текст сообщения.
     * @param {string} type - Тип уведомления ('success' или 'info').
     * @param {string|null} url - URL для перехода по клику.
     * @param {boolean} save - Нужно ли сохранять это уведомление в localStorage.
     */
    function addNotificationToHistory(message, type, url, save = true) {
        if (!notificationHistoryBody) return;

        const item = document.createElement(url ? 'a' : 'div');
        if (url) {
            item.href = url;
            item.target = "_blank"; // Открывать в новой вкладке
            item.className = "block hover:bg-gray-50";
        }

        const typeColor = type === 'success' ? 'border-green-500' : 'border-blue-500';
        const content = document.createElement('div');
        content.className = `p-2 border-l-4 ${typeColor} text-sm text-gray-700 border-b border-gray-200`;
        content.textContent = message;
        item.appendChild(content);

        notificationHistoryBody.prepend(item);

        if (save) {
            const history = JSON.parse(localStorage.getItem(NOTIFICATION_HISTORY_KEY) || '[]');
            history.unshift({ message, type, url });
            if (history.length > MAX_HISTORY_ITEMS) {
                history.pop(); // Удаляем самое старое, если превышен лимит
            }
            localStorage.setItem(NOTIFICATION_HISTORY_KEY, JSON.stringify(history));
        }
    }

    /**
     * Создает всплывающее "тост"-уведомление.
     * @param {string} message - Текст сообщения.
     * @param {string} type - Тип ('success', 'info', 'error').
     * @param {string|null} url - URL для перехода по клику.
     */
    function createToast(message, type = 'info', url = null) {
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'fixed top-5 right-5 z-50 space-y-3 w-full max-w-sm';
            document.body.appendChild(toastContainer);
        }
        
        addNotificationToHistory(message, type, url);

        const toast = document.createElement('div');
        const icons = {
            info: '<svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
            success: '<svg class="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
            error: '<svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
        };
        const colors = {
            info: 'bg-blue-50 border-blue-400',
            success: 'bg-green-50 border-green-400',
            error: 'bg-red-50 border-red-400'
        };
        
        toast.className = `toast-item w-full shadow-lg rounded-lg pointer-events-auto ring-1 ring-black ring-opacity-5 overflow-hidden transform transition-all duration-300 ease-in-out ${colors[type] || colors['info']}`;
        
        let content = `<div class="p-4"><div class="flex items-start"><div class="flex-shrink-0">${icons[type] || icons['info']}</div><div class="ml-3 w-0 flex-1 pt-0.5"><p class="text-sm font-medium text-gray-900">${message}</p></div><div class="ml-4 flex-shrink-0 flex"><button class="inline-flex text-gray-400 hover:text-gray-500" onclick="this.closest('.toast-item').remove()"><span class="sr-only">Close</span><svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg></button></div></div></div>`;

        // Если есть URL, оборачиваем контент в ссылку
        if (url) {
            toast.innerHTML = `<a href="${url}" target="_blank" class="block hover:bg-gray-100">${content}</a>`;
            toast.style.cursor = 'pointer';
        } else {
            toast.innerHTML = content;
        }

        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-20px)';
            setTimeout(() => toast.remove(), 300);
        }, 8000); // Увеличим время отображения до 8 секунд
    }
    
    // Делаем функцию createToast глобально доступной
    window.createToast = createToast;

    // Инициализация WebSocket
    const socket = io();
    socket.on('connect', function() { console.log('WebSocket connected!'); });
    socket.on('notification', function(data) {
        console.log('Received notification:', data);
        const type = data.event.includes('deleted') || data.message.toLowerCase().includes('брак') ? 'error' : (data.event.includes('created') || data.event.includes('completed') ? 'success' : 'info');
        createToast(data.message, type, data.url);
    });
    
    // Управление панелью истории уведомлений
    const historyHeader = document.getElementById('notification-history-header');
    const historyPanel = document.getElementById('notification-history-panel');
    const historyIcon = document.getElementById('history-toggle-icon');
    if(historyHeader) {
        historyHeader.addEventListener('click', () => {
            historyPanel.classList.toggle('is-open');
            historyIcon.textContent = historyPanel.classList.contains('is-open') ? '▼' : '▲';
        });
    }

    loadHistoryFromStorage();
    
    // Обработка форм с подтверждением через SweetAlert2
    document.body.addEventListener('submit', function(event) {
        const form = event.target.closest('.form-confirm');
        if (form) {
            event.preventDefault();
            const confirmText = form.dataset.text || 'Это действие необратимо!';
            Swal.fire({
                title: 'Вы уверены?', text: confirmText, icon: 'warning',
                showCancelButton: true, confirmButtonColor: '#d33', cancelButtonColor: '#3085d6',
                confirmButtonText: 'Да, я уверен!', cancelButtonText: 'Отмена'
            }).then((result) => {
                if (result.isConfirmed) {
                    form.querySelector('button[type="submit"], input[type="submit"]')?.classList.add('is-loading');
                    form.submit();
                }
            });
        }
    });

    // Индикатор загрузки для обычных форм
    document.querySelectorAll('form:not(.form-confirm)').forEach(form => {
        form.addEventListener('submit', function(e) {
            form.querySelector('button[type="submit"], input[type="submit"]')?.classList.add('is-loading');
        });
    });

    // Сброс индикатора загрузки при возврате на страницу
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            document.querySelectorAll('.is-loading').forEach(button => button.classList.remove('is-loading'));
        }
    });
});