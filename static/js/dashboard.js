// static/js/dashboard.js

(function() {
    // File upload
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');

    if (dropZone) {
        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                const file = e.dataTransfer.files[0];
                if (validateFile(file)) {
                    fileInput.files = e.dataTransfer.files;
                    updateFileInfo(file);
                }
            }
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                const file = fileInput.files[0];
                if (validateFile(file)) updateFileInfo(file);
            }
        });
    }

    function validateFile(file) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (ext !== '.docx') {
            showPremiumNotification('Please upload a Word document (.docx) only.', 'error');
            fileInput.value = '';
            return false;
        }
        if (file.size > 16 * 1024 * 1024) {
            showPremiumNotification('File size exceeds 16MB limit.', 'error');
            fileInput.value = '';
            return false;
        }
        return true;
    }

    function updateFileInfo(file) {
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
        if (fileInfo) fileInfo.classList.remove('hidden');
    }

    window.removeFile = function() {
        if (fileInput) fileInput.value = '';
        if (fileInfo) fileInfo.classList.add('hidden');
    };

    // Delete functionality
    let deleteTemplateId = null;
    let deleteTemplateName = '';

    document.addEventListener('DOMContentLoaded', () => {
        // Attach delete handlers to all delete buttons
        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const card = this.closest('.template-card');
                if (card) {
                    const id = card.getAttribute('data-template-id');
                    const name = card.querySelector('h4').textContent;
                    deleteTemplate(id, name);
                }
            });
        });
        
        // Log templates count for debugging
        const templateCards = document.querySelectorAll('.template-card');
        console.log('Templates found:', templateCards.length);
        
        // If no templates, show a message
        if (templateCards.length === 0) {
            console.log('No templates found. Upload a template to get started.');
        }
    });

    function deleteTemplate(id, name) {
        deleteTemplateId = id;
        deleteTemplateName = name;
        const nameSpan = document.getElementById('deleteTemplateName');
        if (nameSpan) nameSpan.textContent = name;
        const modal = document.getElementById('deleteModal');
        if (modal) modal.classList.remove('hidden');
    }

    window.closeDeleteModal = function() {
        const modal = document.getElementById('deleteModal');
        if (modal) modal.classList.add('hidden');
        deleteTemplateId = null;
        deleteTemplateName = '';
    };

    window.confirmDelete = function() {
        if (!deleteTemplateId) return;
        const confirmBtn = document.getElementById('confirmDeleteBtn');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
        }

        fetch('/delete_template/' + deleteTemplateId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showPremiumNotification('Template "' + deleteTemplateName + '" deleted successfully!', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showPremiumNotification('Error: ' + (data.error || 'Unknown error'), 'error');
                window.closeDeleteModal();
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = '<i class="fas fa-trash"></i><span>Delete</span>';
                }
            }
        })
        .catch(err => {
            showPremiumNotification('Error: ' + err.message, 'error');
            window.closeDeleteModal();
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="fas fa-trash"></i><span>Delete</span>';
            }
        });
    };

    // Modal outside click
    const modal = document.getElementById('deleteModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === this) window.closeDeleteModal();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') window.closeDeleteModal();
    });

})();