// static/js/fill_form.js

// Initialize PDF.js
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.10.377/pdf.worker.min.js';

let previewTimeout = null;
let currentPreviewUrl = null;
let isPreviewLoading = false;
let isGenerating = false;
let currentPdfDoc = null;
let generatingFormat = null;
let lastGeneratedFields = null;
let currentRequestId = 0; // Track the current request ID
let activeRequestId = null; // Track the active request being processed
let abortController = null; // For aborting fetch requests

// Get form fields
const form = document.getElementById('formFields');
const inputs = form ? form.querySelectorAll('input[data-field-id]') : [];

// Function to get all field values with their instance IDs
function getFieldValues() {
    const fields = {};
    inputs.forEach(input => {
        const fieldId = input.getAttribute('data-field-id') || input.id;
        const value = input.value; // Don't trim! Keep exact text
        fields[fieldId] = value;
    });
    return fields;
}

// Function to check if any field has value
function hasAnyValue() {
    let hasValues = false;
    inputs.forEach(input => {
        if (input.value) { // Don't trim
            hasValues = true;
        }
    });
    return hasValues;
}

// Function to check if all fields are filled
function areAllFieldsFilled() {
    let allFilled = true;
    inputs.forEach(input => {
        if (!input.value) { // Don't trim
            allFilled = false;
        }
    });
    return allFilled;
}

// Function to update preview with optimized debouncing
function updatePreview() {
    // Clear any existing timeout
    if (previewTimeout) {
        clearTimeout(previewTimeout);
    }

    // Get current field values immediately
    const fields = getFieldValues();
    const currentFieldsString = JSON.stringify(fields);
    
    console.log('Field values changed:', fields);

    // Check if any field has value
    if (!hasAnyValue()) {
        document.getElementById('previewContent').innerHTML = `
            <div class="text-center text-gray-400">
                <i class="fas fa-file-pdf text-6xl mb-4 block"></i>
                <p class="text-lg">No preview available</p>
                <p class="text-sm">Fill in the form fields above to see live preview</p>
            </div>
        `;
        lastGeneratedFields = null;
        return;
    }

    // Check if fields have actually changed since last generation
    if (lastGeneratedFields === currentFieldsString) {
        console.log('Fields unchanged, skipping preview generation');
        return;
    }

    // Use a shorter debounce for faster response - 300ms
    previewTimeout = setTimeout(() => {
        // Double check if fields haven't changed since timeout was set
        const newFields = getFieldValues();
        const newFieldsString = JSON.stringify(newFields);
        
        if (lastGeneratedFields !== newFieldsString) {
            console.log('Generating preview with fields:', newFields);
            lastGeneratedFields = newFieldsString;
            generatePreview();
        }
    }, 300);
}

// Function to generate preview with request cancellation
function generatePreview() {
    // Cancel any ongoing request
    if (abortController) {
        console.log('Aborting previous preview request');
        abortController.abort();
        abortController = null;
    }

    // If there was a loading state, clear it
    isPreviewLoading = false;

    const fields = getFieldValues();
    console.log('Generating preview with fields:', fields);
    
    // Show loading state
    document.getElementById('previewContent').innerHTML = `
        <div class="text-center text-gray-400">
            <i class="fas fa-spinner fa-spin text-4xl mb-4 block"></i>
            <p class="text-lg">Updating preview...</p>
            <p class="text-sm">Please wait while we update the document</p>
        </div>
    `;

    // Increment request ID
    currentRequestId++;
    const thisRequestId = currentRequestId;
    activeRequestId = thisRequestId;
    isPreviewLoading = true;

    const templateId = document.getElementById('templateId').value;
    console.log(`Request ${thisRequestId}: Template ID: ${templateId}`);

    // Create new abort controller
    abortController = new AbortController();

    // Add timestamp to prevent caching
    const timestamp = Date.now();

    fetch(`/generate_preview/${templateId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            fields: fields,
            timestamp: timestamp,
            requestId: thisRequestId
        }),
        signal: abortController.signal
    })
    .then(response => {
        // Check if this request is still the active one
        if (thisRequestId !== activeRequestId) {
            console.log(`Request ${thisRequestId} is no longer active (current: ${activeRequestId}), ignoring response`);
            throw new Error('Request superseded');
        }
        
        console.log(`Request ${thisRequestId}: Response status:`, response.status);
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || 'Network response was not ok');
            });
        }
        return response.json();
    })
    .then(data => {
        // Check if this request is still the active one
        if (thisRequestId !== activeRequestId) {
            console.log(`Request ${thisRequestId} is no longer active (current: ${activeRequestId}), ignoring data`);
            return;
        }
        
        console.log(`Request ${thisRequestId}: Preview response received:`, data);
        isPreviewLoading = false;
        abortController = null;
        
        if (data.success) {
            // Add timestamp to URL to prevent caching
            currentPreviewUrl = data.preview_url + '?t=' + timestamp;
            
            if (data.file_type === 'word') {
                displayWordPreview(currentPreviewUrl);
            } else {
                displayPdfPreview(currentPreviewUrl);
            }
        } else {
            document.getElementById('previewContent').innerHTML = `
                <div class="text-center text-red-500">
                    <i class="fas fa-exclamation-circle text-4xl mb-4 block"></i>
                    <p class="text-lg">Error generating preview</p>
                    <p class="text-sm">${data.error || 'Please try again'}</p>
                </div>
            `;
        }
    })
    .catch(error => {
        // Check if this request is still the active one
        if (thisRequestId !== activeRequestId) {
            console.log(`Request ${thisRequestId} superseded, ignoring error`);
            return;
        }
        
        // Ignore abort errors (they're expected)
        if (error.name === 'AbortError') {
            console.log(`Request ${thisRequestId} was aborted`);
            isPreviewLoading = false;
            abortController = null;
            return;
        }
        
        console.error(`Request ${thisRequestId}: Preview generation error:`, error);
        isPreviewLoading = false;
        abortController = null;
        
        document.getElementById('previewContent').innerHTML = `
            <div class="text-center text-red-500">
                <i class="fas fa-exclamation-circle text-4xl mb-4 block"></i>
                <p class="text-lg">Error generating preview</p>
                <p class="text-sm">${error.message || 'Please try again'}</p>
            </div>
        `;
    });
}

// Function to display PDF preview with ALL pages in scrollable view
function displayPdfPreview(url) {
    const container = document.getElementById('previewContent');
    console.log('Displaying PDF preview:', url);
    
    container.innerHTML = `
        <div class="text-center text-gray-400 py-12">
            <i class="fas fa-spinner fa-spin text-4xl mb-4 block"></i>
            <p class="text-lg">Loading preview...</p>
        </div>
    `;
    
    // Clear previous PDF document
    currentPdfDoc = null;
    
    pdfjsLib.getDocument(url).promise.then(pdf => {
        currentPdfDoc = pdf;
        const totalPages = pdf.numPages;
        console.log('PDF loaded, pages:', totalPages);
        
        container.innerHTML = `
            <div id="pdfViewer" class="w-full h-full overflow-auto">
                <div id="pdfPagesWrapper" class="flex flex-col items-center gap-6 p-4">
                </div>
            </div>
        `;
        
        renderAllPages(pdf, totalPages);
        
    }).catch(error => {
        console.error('Error rendering PDF:', error);
        // If PDF fails to load, try again after a short delay
        setTimeout(() => {
            if (currentPreviewUrl) {
                displayPdfPreview(currentPreviewUrl);
            }
        }, 500);
    });
}

// Function to render ALL pages of the PDF
function renderAllPages(pdf, totalPages) {
    const wrapper = document.getElementById('pdfPagesWrapper');
    if (!wrapper) return;
    
    const container = document.getElementById('previewContent');
    const containerWidth = container.clientWidth - 40;
    
    const renderPromises = [];
    
    for (let i = 1; i <= totalPages; i++) {
        renderPromises.push(
            pdf.getPage(i).then(page => {
                const viewport = page.getViewport({ scale: 1 });
                const scale = containerWidth / viewport.width;
                const scaledViewport = page.getViewport({ scale: scale });
                
                const pageWrapper = document.createElement('div');
                pageWrapper.className = 'pdf-page-wrapper';
                pageWrapper.style.width = '100%';
                pageWrapper.style.display = 'flex';
                pageWrapper.style.flexDirection = 'column';
                pageWrapper.style.alignItems = 'center';
                pageWrapper.style.marginBottom = '20px';
                
                const canvas = document.createElement('canvas');
                canvas.id = `pdfPage_${i}_${Date.now()}`;
                canvas.style.width = '100%';
                canvas.style.height = 'auto';
                canvas.style.maxWidth = scaledViewport.width + 'px';
                canvas.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
                canvas.style.borderRadius = '4px';
                canvas.style.backgroundColor = 'white';
                
                const pageLabel = document.createElement('div');
                pageLabel.className = 'text-xs text-gray-500 text-center mt-2';
                pageLabel.textContent = `Page ${i} of ${totalPages}`;
                
                pageWrapper.appendChild(canvas);
                pageWrapper.appendChild(pageLabel);
                wrapper.appendChild(pageWrapper);
                
                const ctx = canvas.getContext('2d');
                canvas.width = scaledViewport.width;
                canvas.height = scaledViewport.height;
                
                const renderContext = {
                    canvasContext: ctx,
                    viewport: scaledViewport
                };
                
                return page.render(renderContext).promise;
            })
        );
    }
    
    Promise.all(renderPromises).then(() => {
        console.log(`All ${totalPages} pages rendered successfully`);
    }).catch(error => {
        console.error('Error rendering pages:', error);
    });
}

// Function to display Word preview (download link)
function displayWordPreview(url) {
    const container = document.getElementById('previewContent');
    console.log('Displaying Word preview:', url);
    
    container.innerHTML = `
        <div class="text-center text-gray-600 py-12">
            <i class="fas fa-file-word text-6xl text-blue-500 mb-4 block"></i>
            <p class="text-lg font-medium">Word Document Preview</p>
            <p class="text-sm text-gray-400 mb-6">Preview not available for Word documents. Download to view.</p>
            <div class="flex justify-center gap-4">
                <a href="${url}" target="_blank" class="inline-flex items-center px-6 py-3 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition">
                    <i class="fas fa-download mr-2"></i>
                    Download Preview
                </a>
                <button onclick="generateDocument('word')" class="inline-flex items-center px-6 py-3 bg-emerald-500 text-white rounded-xl hover:bg-emerald-600 transition">
                    <i class="fas fa-file-word mr-2"></i>
                    Generate Word
                </button>
            </div>
        </div>
    `;
}

// Function to generate final document
function generateDocument(format) {
    if (isGenerating) {
        showNotification('Please wait, document is being generated...', 'info');
        return;
    }
    
    if (!areAllFieldsFilled()) {
        showNotification('Please fill out all fields to generate the document', 'warning');
        return;
    }
    
    const formData = new FormData();
    inputs.forEach(input => {
        const fieldId = input.getAttribute('data-field-id') || input.id;
        formData.append(fieldId, input.value); // Don't trim
    });
    formData.append('format', format);

    isGenerating = true;
    generatingFormat = format;

    let targetButton = null;
    const buttons = document.querySelectorAll('button[onclick^="generateDocument"]');
    buttons.forEach(btn => {
        if (btn.getAttribute('onclick').includes(`'${format}'`)) {
            targetButton = btn;
        }
        btn.disabled = true;
    });

    if (targetButton) {
        targetButton.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Generating ${format.toUpperCase()}...`;
    } else {
        buttons.forEach(btn => {
            btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Generating...`;
        });
    }

    const templateId = document.getElementById('templateId').value;

    fetch(`/generate/${templateId}`, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                try {
                    const json = JSON.parse(text);
                    throw new Error(json.error || 'Generation failed');
                } catch {
                    throw new Error(text || 'Generation failed');
                }
            });
        }
        return response.blob();
    })
    .then(blob => {
        if (!blob || blob.size === 0) {
            throw new Error('Generated file is empty');
        }
        
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document.${format === 'word' ? 'docx' : 'pdf'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showNotification(`${format.toUpperCase()} generated successfully!`, 'success');
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error generating document: ' + error.message, 'error');
    })
    .finally(() => {
        const buttons = document.querySelectorAll('button[onclick^="generateDocument"]');
        buttons.forEach(btn => {
            btn.disabled = false;
            if (btn.getAttribute('onclick').includes('pdf')) {
                btn.innerHTML = `<i class="fas fa-file-pdf text-lg"></i><span>Generate PDF</span>`;
            } else if (btn.getAttribute('onclick').includes('word')) {
                btn.innerHTML = `<i class="fas fa-file-word text-lg"></i><span>Generate Word</span>`;
            } else {
                if (btn.textContent.includes('PDF')) {
                    btn.innerHTML = `<i class="fas fa-file-pdf text-lg"></i><span>Generate PDF</span>`;
                } else {
                    btn.innerHTML = `<i class="fas fa-file-word text-lg"></i><span>Generate Word</span>`;
                }
            }
        });
        isGenerating = false;
        generatingFormat = null;
    });
}

// Notification function
function showNotification(message, type = 'info') {
    const colors = {
        success: 'bg-emerald-500',
        error: 'bg-red-500',
        info: 'bg-blue-500',
        warning: 'bg-yellow-500'
    };
    
    const existing = document.querySelectorAll('.notification-toast');
    existing.forEach(el => el.remove());
    
    const notification = document.createElement('div');
    notification.className = `notification-toast fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-xl shadow-lg z-50 transform transition-all duration-500 translate-x-full`;
    notification.innerHTML = `
        <div class="flex items-center gap-3">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'}"></i>
            <span>${message}</span>
        </div>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.remove('translate-x-full');
    }, 100);
    
    setTimeout(() => {
        notification.classList.add('translate-x-full');
        setTimeout(() => {
            notification.remove();
        }, 500);
    }, 5000);
}

// Add event listeners to inputs - IMMEDIATE response
inputs.forEach(input => {
    // Remove any existing listeners to avoid duplicates
    input.removeEventListener('input', updatePreview);
    input.removeEventListener('keyup', updatePreview);
    input.removeEventListener('paste', updatePreview);
    input.removeEventListener('change', updatePreview);
    
    // Use 'input' event for live updates on every keystroke
    input.addEventListener('input', function(e) {
        console.log(`Input event on ${this.id}: "${this.value}"`);
        // Update immediately on each keystroke
        updatePreview();
    });
    
    // Also listen for keyup as a fallback for paste events
    input.addEventListener('keyup', function(e) {
        // Only trigger if not already triggered by input event
        if (e.key === 'Enter') {
            updatePreview();
        }
    });
    
    // Listen for paste events and update immediately
    input.addEventListener('paste', function(e) {
        console.log(`Paste event on ${this.id}`);
        // Small delay to let the paste complete
        setTimeout(() => {
            updatePreview();
        }, 50);
    });
    
    // Listen for change events (for autofill or programmatic changes)
    input.addEventListener('change', function(e) {
        console.log(`Change event on ${this.id}: "${this.value}"`);
        updatePreview();
    });
    
    console.log('Added input listeners to:', input.id);
});

// Handle window resize for PDF viewer
let resizeTimeout;
window.addEventListener('resize', () => {
    if (currentPdfDoc) {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            const container = document.getElementById('previewContent');
            const url = currentPreviewUrl;
            if (url && currentPdfDoc) {
                displayPdfPreview(url);
            }
        }, 500);
    }
});

// Expose functions to global scope
window.generateDocument = generateDocument;
window.updatePreview = updatePreview;
window.generatePreview = generatePreview;

// Initial preview after page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, setting up initial preview');
    
    // Reset last generated fields
    lastGeneratedFields = null;
    currentRequestId = 0;
    activeRequestId = null;
    
    // Check if any fields have values
    if (hasAnyValue()) {
        console.log('Pre-filled values detected, generating initial preview');
        setTimeout(updatePreview, 300);
    }
});

// Manual refresh function for debugging
window.refreshPreview = function() {
    console.log('Manual refresh triggered');
    lastGeneratedFields = null;
    // Reset request tracking
    currentRequestId = 0;
    activeRequestId = null;
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
    generatePreview();
};

// Force immediate preview update on field focus
inputs.forEach(input => {
    input.addEventListener('focus', function() {
        console.log('Field focused:', this.id);
        // If there's a value, update preview
        if (this.value) {
            updatePreview();
        }
    });
});

// Force preview update on field blur
inputs.forEach(input => {
    input.addEventListener('blur', function() {
        console.log('Field blurred:', this.id);
        // Always update on blur to ensure final value is captured
        setTimeout(() => {
            updatePreview();
        }, 100);
    });
});

console.log('fill_form.js loaded successfully with request cancellation');