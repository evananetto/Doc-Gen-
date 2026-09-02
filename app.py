# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify, send_from_directory
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from utils.parser import parse_template, iter_all_paragraphs, is_run_effectively_bold, clean_extracted_field, extract_bold_instances_from_docx
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
import json
import io
import shutil
import subprocess
import tempfile
import sys
import traceback

# Import preview functionality
from preview import create_preview_response, cleanup_old_previews

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
STATIC_FOLDER = 'static'
ALLOWED_EXTENSIONS = {'docx'}
TEMPLATES_FILE = 'templates_data.json'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.join(STATIC_FOLDER, 'previews'), exist_ok=True)

# Hardcoded login credentials
USER_CREDENTIALS = {
    os.environ.get('ADMIN_USERNAME', 'admin'): os.environ.get('ADMIN_PASSWORD', 'admin@123')
}

# ============= TEMPLATE STORAGE FUNCTIONS =============

def load_templates():
    """Load templates from JSON file"""
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE, 'r') as f:
                templates = json.load(f)
                # Ensure all fields have all_run_indices
                for template in templates:
                    if 'fields' in template:
                        for field in template['fields']:
                            if 'all_run_indices' not in field:
                                # If missing, try to reconstruct from run_id
                                field['all_run_indices'] = []
                return templates
        except Exception as e:
            print(f"Error loading templates: {e}")
            return []
    return []

def save_templates(templates):
    """Save templates to JSON file"""
    try:
        with open(TEMPLATES_FILE, 'w') as f:
            json.dump(templates, f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error saving templates: {e}")
        return False

# ============= END TEMPLATE STORAGE FUNCTIONS =============

def find_libreoffice():
    """Find LibreOffice executable path on Windows"""
    if os.name == 'nt':  # Windows
        possible_paths = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    return 'soffice'  # For Linux/Mac, assume it's in PATH


def store_recent_document(template_name, filename, file_type, file_path):
    """Store document in recent documents list"""
    if 'recent_documents' not in session:
        session['recent_documents'] = []

    doc_info = {
        'id': len(session['recent_documents']) + 1,
        'name': template_name,
        'filename': filename,
        'file_type': file_type,
        'file_path': file_path,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
    }

    session['recent_documents'].insert(0, doc_info)
    if len(session['recent_documents']) > 20:
        session['recent_documents'] = session['recent_documents'][:20]
    session.modified = True


# ---------------------------------------------------------------------------
# Core replacement logic - FIXED: Replaces ALL runs in a merged group
# ---------------------------------------------------------------------------

def generate_word_from_template_preserve_formatting(template_path, field_mappings, output_path):
    """
    Generate Word document by replacing ONLY the exact bold run identified
    by each field mapping's run_id.
    
    CRITICAL FIX: Replaces ALL runs in a merged group, not just the first run.
    This ensures special characters like '/', '.', '&' are completely replaced.
    """
    try:
        doc = Document(template_path)

        print("=" * 60)
        print("DEBUG: Starting document generation with replacements")
        print("=" * 60)
        print(f"DEBUG: Field mappings: {field_mappings}")
        print(f"DEBUG: Total fields to replace: {len(field_mappings)}")

        # Build a lookup: run_id -> field_value and all_run_indices
        replacements_by_run_id = {}
        for mapping in field_mappings:
            run_id = mapping.get('run_id')
            field_value = mapping.get('field_value', '')
            original_text = mapping.get('original_text', mapping.get('field_name', ''))
            all_run_indices = mapping.get('all_run_indices', [])

            print(f"DEBUG: Processing mapping - run_id={run_id}, value='{field_value}', all_run_indices={all_run_indices}")

            if field_value is None or field_value == '':
                print(f"DEBUG: Skipping empty value for {run_id}")
                continue

            if run_id:
                # Store the complete information for this replacement
                replacements_by_run_id[run_id] = {
                    'value': field_value,
                    'original': original_text,
                    'all_run_indices': all_run_indices
                }
                print(f"DEBUG: Will replace run_id {run_id} with '{field_value}' (was '{original_text}')")
                if all_run_indices:
                    print(f"DEBUG: Will also replace these additional runs: {all_run_indices}")
            else:
                print(f"WARNING: mapping for '{original_text}' has no run_id - skipping")

        print(f"DEBUG: Replacements to apply: {replacements_by_run_id}")
        print("=" * 60)

        total_replaced = 0

        def process_paragraphs_for_replace(paragraphs, location_prefix):
            """Walk paragraphs/runs in EXACTLY the same order as parser"""
            count = 0
            for p_idx, paragraph in enumerate(paragraphs):
                if not paragraph.text.strip():
                    continue
                
                # Check if this paragraph has any replacements
                has_replacement = False
                for r_idx, run in enumerate(paragraph.runs):
                    run_id = f"{location_prefix}:{p_idx}:{r_idx}"
                    if run_id in replacements_by_run_id:
                        has_replacement = True
                        break
                
                if not has_replacement:
                    continue
                
                print(f"DEBUG: Processing paragraph {p_idx} with {len(paragraph.runs)} runs")
                
                # Process runs and replace ALL runs in the merged group
                for r_idx, run in enumerate(paragraph.runs):
                    run_id = f"{location_prefix}:{p_idx}:{r_idx}"
                    
                    if run_id in replacements_by_run_id:
                        replacement_data = replacements_by_run_id[run_id]
                        field_value = replacement_data['value']
                        all_run_indices = replacement_data.get('all_run_indices', [])
                        
                        print(f"DEBUG: Found replacement for run_id {run_id}")
                        print(f"DEBUG: Current run text: '{run.text}'")
                        print(f"DEBUG: Replacing with: '{field_value}'")
                        print(f"DEBUG: All run indices to clear: {all_run_indices}")
                        
                        # Replace this run
                        run.text = field_value
                        count += 1
                        print(f"DEBUG: Replaced run_id {run_id} with '{field_value}'")
                        
                        # Also replace all other runs in the merged group with EMPTY string
                        if all_run_indices:
                            for extra_idx in all_run_indices:
                                if extra_idx != r_idx and extra_idx < len(paragraph.runs):
                                    old_text = paragraph.runs[extra_idx].text
                                    paragraph.runs[extra_idx].text = ""
                                    print(f"DEBUG: Cleared extra run index {extra_idx} (was '{old_text}')")
            
            return count

        # Process body paragraphs
        body_paragraphs = list(iter_all_paragraphs(doc))
        body_count = process_paragraphs_for_replace(body_paragraphs, "body")
        print(f"DEBUG: Replaced {body_count} run(s) in body/tables")
        total_replaced += body_count

        # Process headers and footers
        header_footer_count = 0
        for section_idx, section in enumerate(doc.sections):
            header_paragraphs = list(iter_all_paragraphs(section.header))
            header_footer_count += process_paragraphs_for_replace(header_paragraphs, f"header_{section_idx}")

            footer_paragraphs = list(iter_all_paragraphs(section.footer))
            header_footer_count += process_paragraphs_for_replace(footer_paragraphs, f"footer_{section_idx}")

        print(f"DEBUG: Replaced {header_footer_count} run(s) in headers/footers")
        total_replaced += header_footer_count

        print(f"DEBUG: Total replacements: {total_replaced}")
        print("=" * 60)

        # Save the document
        doc.save(output_path)
        print(f"DEBUG: Word document saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error generating Word with preserved formatting: {e}")
        traceback.print_exc()
        return False


def convert_word_to_pdf(word_path, pdf_path):
    """Convert Word to PDF while preserving formatting using LibreOffice"""
    try:
        if not os.path.exists(word_path):
            print(f"Word file not found: {word_path}")
            return False

        if os.path.getsize(word_path) == 0:
            print(f"Word file is empty: {word_path}")
            return False

        libreoffice_path = find_libreoffice()

        if os.name == 'nt' and not os.path.exists(libreoffice_path):
            print(f"LibreOffice not found at: {libreoffice_path}")
            return False

        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        abs_word_path = os.path.abspath(word_path)
        abs_pdf_path = os.path.abspath(pdf_path)

        cmd = [
            libreoffice_path,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(abs_pdf_path),
            abs_word_path
        ]

        print(f"Running command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        if result.returncode == 0:
            expected_pdf = abs_word_path.replace('.docx', '.pdf')
            if os.path.exists(expected_pdf):
                if os.path.getsize(expected_pdf) > 0:
                    shutil.move(expected_pdf, abs_pdf_path)
                    return True
                else:
                    print(f"PDF file is empty: {expected_pdf}")
                    return False
            else:
                print(f"Expected PDF not found: {expected_pdf}")
                return False

        return False
    except subprocess.TimeoutExpired:
        print("Timeout converting Word to PDF")
        return False
    except Exception as e:
        print(f"Error converting Word to PDF: {e}")
        traceback.print_exc()
        return False


def validate_pdf(file_path):
    """Validate if a file is a proper PDF"""
    try:
        if not os.path.exists(file_path):
            return False
        if os.path.getsize(file_path) == 0:
            return False
        doc = fitz.open(file_path)
        doc.close()
        return True
    except:
        return False


# ============= ROUTES =============

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'danger')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'template' not in request.files:
            flash('No file selected!', 'danger')
            return redirect(url_for('dashboard'))

        file = request.files['template']
        template_name = request.form.get('templateName', '')

        if file.filename == '':
            flash('No file selected!', 'danger')
            return redirect(url_for('dashboard'))

        if not template_name:
            flash('Please enter a template name!', 'danger')
            return redirect(url_for('dashboard'))

        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext != 'docx':
            flash('Only Word documents (.docx) are allowed!', 'danger')
            return redirect(url_for('dashboard'))

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
        file.save(file_path)

        try:
            # Extract bold instances with full position info
            bold_instances = extract_bold_instances_from_docx(file_path)
            print(f"DEBUG: Total bold instances extracted: {len(bold_instances)}")

            if bold_instances:
                print("DEBUG: All extracted bold instances:")
                for idx, instance in enumerate(bold_instances, 1):
                    print(f"  {idx}. ID: {instance.get('id', '')}, "
                          f"Text: '{instance.get('text', '')}', "
                          f"run_id: {instance.get('run_id', '')}, "
                          f"merged_count: {instance.get('merged_count', 1)}, "
                          f"all_run_indices: {instance.get('all_run_indices', [])}")
            else:
                print("DEBUG: No bold text extracted from the document")
                flash('No bold text found in the document. Please ensure your document has bold text.', 'warning')

        except Exception as e:
            flash(f'Error parsing template: {str(e)}', 'danger')
            return redirect(url_for('dashboard'))

        templates = load_templates()
        
        template_info = {
            'id': len(templates) + 1,
            'name': template_name,
            'filename': saved_filename,
            'original_filename': filename,
            'file_type': file_ext,
            'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'file_path': file_path,
            'fields': bold_instances
        }
        
        templates.append(template_info)
        save_templates(templates)
        
        print(f"DEBUG: Template added. Total templates in file: {len(templates)}")

        flash(f'Template "{template_name}" uploaded successfully! Found {len(bold_instances)} bold text instances.', 'success')
        return redirect(url_for('dashboard'))

    templates = load_templates()
    print(f"DEBUG: Rendering dashboard with {len(templates)} templates")
    return render_template('dashboard.html', username=session.get('username'), templates=templates)


@app.route('/fill/<int:template_id>')
def fill_form(template_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    templates = load_templates()
    template = None

    for t in templates:
        if t.get('id') == template_id:
            template = t
            break

    if not template:
        flash('Template not found!', 'danger')
        return redirect(url_for('dashboard'))

    bold_instances = template.get('fields', [])

    # Ensure all instances have proper structure
    converted_instances = []
    for instance in bold_instances:
        if isinstance(instance, dict):
            if 'run_id' not in instance:
                if 'paragraph_index' in instance and 'run_index' in instance:
                    instance['run_id'] = f"body:{instance['paragraph_index']}:{instance['run_index']}"
                else:
                    instance['run_id'] = None
            # Ensure all_run_indices exists
            if 'all_run_indices' not in instance:
                instance['all_run_indices'] = []
            converted_instances.append(instance)
        elif isinstance(instance, str):
            converted_instances.append({
                'id': f'field_{len(converted_instances) + 1}',
                'text': instance,
                'original_text': instance,
                'instance_number': len(converted_instances) + 1,
                'context': '',
                'context_before': '',
                'context_after': '',
                'paragraph_text': '',
                'field_position': len(converted_instances) + 1,
                'location': None,
                'paragraph_index': None,
                'run_index': None,
                'run_id': None,
                'all_run_indices': [],
                'merged_count': 1
            })

    file_type = template.get('file_type', 'docx')

    return render_template('fill_form.html',
                         username=session.get('username'),
                         template=template,
                         bold_instances=converted_instances,
                         file_type=file_type)


@app.route('/generate_preview/<int:template_id>', methods=['POST'])
def generate_preview(template_id):
    """Generate a preview of the document with filled fields"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    templates = load_templates()
    template = None
    for t in templates:
        if t.get('id') == template_id:
            template = t
            break

    if not template:
        return jsonify({'error': 'Template not found'}), 404

    data = request.json
    field_values = data.get('fields', {})

    # Use the preview module to generate the preview
    # Pass the required functions to avoid circular imports
    result = create_preview_response(
        template, 
        field_values, 
        app.config['STATIC_FOLDER'],
        generate_word_from_template_preserve_formatting,
        convert_word_to_pdf,
        validate_pdf
    )
    
    if result.get('success'):
        return jsonify({
            'success': True,
            'preview_url': result.get('preview_url'),
            'file_type': result.get('file_type'),
            'message': result.get('message', '')
        })
    else:
        return jsonify({
            'error': result.get('error', 'Failed to generate preview')
        }), 500


@app.route('/generate/<int:template_id>', methods=['POST'])
def generate_document(template_id):
    """Generate and download the final document"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    form_data = request.form
    format_type = form_data.get('format', 'pdf')

    templates = load_templates()
    template = None
    for t in templates:
        if t.get('id') == template_id:
            template = t
            break

    if not template:
        flash('Template not found!', 'danger')
        return redirect(url_for('dashboard'))

    bold_instances = template.get('fields', [])

    # Create field mappings with unique instance IDs AND exact run_id AND all_run_indices
    field_mappings = []
    for i, instance in enumerate(bold_instances, 1):
        value = form_data.get(f'field_{i}', '')
        if value and value.strip():
            # Get the original text from the instance
            original_text = instance.get('text', '')
            run_id = instance.get('run_id')
            all_run_indices = instance.get('all_run_indices', [])
            
            print(f"DEBUG: Field {i} - original='{original_text}', run_id={run_id}, all_run_indices={all_run_indices}")
            
            if not run_id and 'paragraph_index' in instance and 'run_index' in instance:
                run_id = f"body:{instance['paragraph_index']}:{instance['run_index']}"
            
            mapping = {
                'instance_id': f'field_{i}',
                'field_name': original_text,
                'original_text': original_text,
                'field_value': value,
                'field_index': i,
                'run_id': run_id,
                'all_run_indices': all_run_indices  # CRITICAL: Pass all run indices
            }
            
            field_mappings.append(mapping)
            print(f"DEBUG: Mapping field_{i}: "
                  f"'{original_text}' -> '{value}' (run_id={run_id}, all_run_indices={all_run_indices})")

    template_path = template.get('file_path')
    file_type = template.get('file_type', 'docx')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    print(f"DEBUG generate_document: File type: {file_type}, Format: {format_type}")
    print(f"DEBUG generate_document: Field mappings: {field_mappings}")

    if file_type == 'docx':
        temp_word_path = os.path.join(app.config['OUTPUT_FOLDER'], f"temp_{timestamp}.docx")
        word_success = generate_word_from_template_preserve_formatting(template_path, field_mappings, temp_word_path)

        if not word_success:
            flash('Error generating document!', 'danger')
            return redirect(url_for('fill_form', template_id=template_id))

        if format_type == 'word':
            output_filename = f"document_{timestamp}.docx"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            shutil.copy2(temp_word_path, output_path)

            if os.path.exists(temp_word_path):
                os.remove(temp_word_path)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                store_recent_document(template.get('name', 'Document'), output_filename, 'word', output_path)
                flash('Word document generated successfully!', 'success')
                return send_file(output_path, as_attachment=True, download_name=output_filename)
            else:
                flash('Error generating Word document!', 'danger')
                return redirect(url_for('fill_form', template_id=template_id))

        else:  # format_type == 'pdf'
            output_filename = f"document_{timestamp}.pdf"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            pdf_success = convert_word_to_pdf(temp_word_path, output_path)

            if os.path.exists(temp_word_path):
                os.remove(temp_word_path)

            if pdf_success and validate_pdf(output_path):
                store_recent_document(template.get('name', 'Document'), output_filename, 'pdf', output_path)
                flash('PDF generated successfully!', 'success')
                return send_file(output_path, as_attachment=True, download_name=output_filename)
            else:
                flash('Could not convert Word to PDF. Downloading Word document instead.', 'warning')
                output_filename = f"document_{timestamp}.docx"
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
                word_success = generate_word_from_template_preserve_formatting(template_path, field_mappings, output_path)
                if word_success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    store_recent_document(template.get('name', 'Document'), output_filename, 'word', output_path)
                    return send_file(output_path, as_attachment=True, download_name=output_filename)
                else:
                    flash('Error generating document!', 'danger')
                    return redirect(url_for('fill_form', template_id=template_id))
    else:
        flash('Unsupported file type!', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/recent')
def recent_documents():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    recent_docs = session.get('recent_documents', [])
    return render_template('recent_documents.html',
                         username=session.get('username'),
                         documents=recent_docs)


@app.route('/download/<int:doc_id>')
def download_document(doc_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    recent_docs = session.get('recent_documents', [])
    doc = None

    for d in recent_docs:
        if d.get('id') == doc_id:
            doc = d
            break

    if not doc:
        flash('Document not found!', 'danger')
        return redirect(url_for('recent_documents'))

    file_path = doc.get('file_path')
    filename = doc.get('filename')

    if not os.path.exists(file_path):
        flash('File not found!', 'danger')
        return redirect(url_for('recent_documents'))

    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route('/delete_template/<int:template_id>', methods=['POST'])
def delete_template(template_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    templates = load_templates()
    template_to_delete = None

    for t in templates:
        if t.get('id') == template_id:
            template_to_delete = t
            break

    if template_to_delete:
        file_path = template_to_delete.get('file_path')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

        templates = [t for t in templates if t.get('id') != template_id]
        save_templates(templates)

        return jsonify({'success': True})

    return jsonify({'error': 'Template not found'}), 404


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


@app.route('/check_libreoffice')
def check_libreoffice():
    try:
        libreoffice_path = find_libreoffice()

        if not os.path.exists(libreoffice_path) and libreoffice_path == 'soffice':
            import shutil
            path = shutil.which('soffice')
            if path:
                libreoffice_path = path
            else:
                return jsonify({
                    'installed': False,
                    'error': f'LibreOffice not found. Please install LibreOffice from https://www.libreoffice.org/'
                })

        cmd = [libreoffice_path, '--version']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            return jsonify({
                'installed': True,
                'path': libreoffice_path,
                'version': result.stdout.strip()
            })
        else:
            return jsonify({
                'installed': False,
                'path': libreoffice_path,
                'error': 'Version check failed',
                'stderr': result.stderr
            })
    except Exception as e:
        return jsonify({
            'installed': False,
            'error': str(e)
        })


@app.route('/debug_fields/<int:template_id>')
def debug_fields(template_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    templates = load_templates()
    template = None

    for t in templates:
        if t.get('id') == template_id:
            template = t
            break

    if not template:
        return jsonify({'error': 'Template not found'}), 404

    bold_instances = template.get('fields', [])

    return jsonify({
        'template_name': template.get('name'),
        'total_instances': len(bold_instances),
        'bold_instances': bold_instances,
        'file_path': template.get('file_path'),
        'file_type': template.get('file_type')
    })


# ============= CACHE CONTROL FOR PREVIEWS =============

@app.route('/static/previews/<path:filename>')
def serve_preview(filename):
    """Serve preview files with no-cache headers for immediate updates"""
    response = send_from_directory(os.path.join(app.config['STATIC_FOLDER'], 'previews'), filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


if __name__ == '__main__':
    app.run(debug=True, port=2000)