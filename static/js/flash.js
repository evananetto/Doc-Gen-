// static/js/flash.js

(function() {
    'use strict';

    // Auto-dismiss flash messages with progress bar
    document.addEventListener('DOMContentLoaded', function() {
        const flashMessages = document.querySelectorAll('.flash-message');
        
        flashMessages.forEach((msg, index) => {
            const progress = msg.querySelector('.flash-progress-bar');
            const toast = msg.querySelector('.bg-white\\/95');
            
            // Stagger the appearance
            setTimeout(() => {
                msg.classList.add('flash-enter');
            }, index * 100);
            
            // Progress bar animation
            let width = 100;
            const interval = setInterval(() => {
                width -= 0.5; // 5000ms / 100 = 50ms per step
                if (progress) {
                    progress.style.width = width + '%';
                }
                if (width <= 0) {
                    clearInterval(interval);
                    closeFlashMessage(msg);
                }
            }, 50);
            
            // Store interval for cleanup
            msg._interval = interval;
            
            // Pause on hover
            if (toast) {
                toast.addEventListener('mouseenter', () => {
                    clearInterval(msg._interval);
                });
                
                toast.addEventListener('mouseleave', () => {
                    let currentWidth = progress ? parseFloat(progress.style.width) : 100;
                    msg._interval = setInterval(() => {
                        currentWidth -= 0.5;
                        if (progress) {
                            progress.style.width = currentWidth + '%';
                        }
                        if (currentWidth <= 0) {
                            clearInterval(msg._interval);
                            closeFlashMessage(msg);
                        }
                    }, 50);
                });
            }
        });
    });

    // Close flash message from button click
    window.closeFlash = function(button) {
        const msg = button.closest('.flash-message');
        if (msg) {
            closeFlashMessage(msg);
        }
    };

    // Close flash message with animation
    function closeFlashMessage(msg) {
        if (msg._interval) {
            clearInterval(msg._interval);
        }
        msg.classList.remove('flash-enter');
        msg.classList.add('flash-exit');
        setTimeout(() => {
            msg.remove();
            // Check if container is empty and hide if needed
            const container = document.getElementById('flashContainer');
            if (container && container.children.length === 0) {
                container.style.display = 'none';
            }
        }, 300);
    }

    // Global function for JS-generated notifications (premium style)
    window.showPremiumNotification = function(message, type = 'info', title = null) {
        const container = document.getElementById('flashContainer');
        if (!container) return;
        
        container.style.display = 'flex';
        
        const titles = {
            success: 'Success',
            error: 'Error',
            warning: 'Warning',
            info: 'Info'
        };
        
        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };
        
        const colorClasses = {
            success: 'border-l-emerald-500',
            error: 'border-l-rose-500',
            warning: 'border-l-amber-500',
            info: 'border-l-indigo-500'
        };
        
        const iconBgClasses = {
            success: 'bg-emerald-50 text-emerald-600',
            error: 'bg-rose-50 text-rose-600',
            warning: 'bg-amber-50 text-amber-600',
            info: 'bg-indigo-50 text-indigo-600'
        };
        
        const progressClasses = {
            success: 'bg-gradient-to-r from-emerald-500 to-emerald-300',
            error: 'bg-gradient-to-r from-rose-500 to-rose-300',
            warning: 'bg-gradient-to-r from-amber-500 to-amber-300',
            info: 'bg-gradient-to-r from-indigo-500 to-indigo-300'
        };
        
        const badgeClasses = {
            success: 'bg-emerald-100 text-emerald-700',
            error: 'bg-rose-100 text-rose-700',
            warning: 'bg-amber-100 text-amber-700',
            info: 'bg-indigo-100 text-indigo-700'
        };
        
        let countBadge = '';
        if (message.includes('Found') && message.includes('bold')) {
            const parts = message.split('Found');
            if (parts.length > 1) {
                const countParts = parts[1].split('bold');
                if (countParts.length > 0) {
                    const count = countParts[0].trim();
                    if (count) {
                        countBadge = `
                            <span class="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-0.5 rounded-full ${badgeClasses[type]}">
                                <i class="fas fa-tag text-[10px]"></i>
                                ${count}
                            </span>
                        `;
                    }
                }
            }
        }
        
        const msgDiv = document.createElement('div');
        msgDiv.className = 'flash-message pointer-events-auto flash-enter';
        
        msgDiv.innerHTML = `
            <div class="bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/60 p-4 flex items-start gap-3.5 relative overflow-hidden border-l-4 ${colorClasses[type]}">
                <div class="w-10 h-10 min-w-[40px] rounded-xl flex items-center justify-center text-lg ${iconBgClasses[type]}">
                    <i class="fas ${icons[type] || icons.info}"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="font-bold text-sm text-slate-800">${title || titles[type] || 'Info'}</span>
                        ${countBadge}
                    </div>
                    <p class="text-sm text-slate-600 font-medium leading-relaxed">${message}</p>
                </div>
                <button onclick="closeFlash(this)" class="w-7 h-7 min-w-[28px] rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all duration-200 hover:rotate-90 mt-[-2px]">
                    <i class="fas fa-times text-sm"></i>
                </button>
                <div class="absolute bottom-0 left-0 h-1 rounded-b-2xl flash-progress-bar ${progressClasses[type]}" style="width: 100%;"></div>
            </div>
        `;
        
        container.appendChild(msgDiv);
        
        // Auto-dismiss
        let width = 100;
        const interval = setInterval(() => {
            width -= 0.5;
            const progress = msgDiv.querySelector('.flash-progress-bar');
            if (progress) {
                progress.style.width = width + '%';
            }
            if (width <= 0) {
                clearInterval(interval);
                closeFlashMessage(msgDiv);
            }
        }, 50);
        
        msgDiv._interval = interval;
        
        // Pause on hover
        const toast = msgDiv.querySelector('.bg-white\\/95');
        if (toast) {
            toast.addEventListener('mouseenter', () => {
                clearInterval(msgDiv._interval);
            });
            
            toast.addEventListener('mouseleave', () => {
                let currentWidth = msgDiv.querySelector('.flash-progress-bar')?.style?.width || '100%';
                currentWidth = parseFloat(currentWidth) || 100;
                msgDiv._interval = setInterval(() => {
                    currentWidth -= 0.5;
                    const progress = msgDiv.querySelector('.flash-progress-bar');
                    if (progress) {
                        progress.style.width = currentWidth + '%';
                    }
                    if (currentWidth <= 0) {
                        clearInterval(msgDiv._interval);
                        closeFlashMessage(msgDiv);
                    }
                }, 50);
            });
        }
        
        return msgDiv;
    };

})();