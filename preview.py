# preview.py

import os
from datetime import datetime
import shutil
import traceback
import time


def cleanup_old_previews(static_folder):
    """Clean up preview files older than 1 hour"""
    preview_dir = os.path.join(static_folder, 'previews')
    current_time = datetime.now()
    try:
        for filename in os.listdir(preview_dir):
            file_path = os.path.join(preview_dir, filename)
            if os.path.isfile(file_path):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (current_time - file_mtime).total_seconds() > 3600:  # 1 hour
                    os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up previews: {e}")


def generate_preview_document(template, field_mappings, static_folder, generate_word_func, convert_pdf_func, validate_pdf_func):
    """
    Generate a preview document with filled fields
    Pass the required functions as parameters to avoid circular imports
    """
    try:
        template_path = template.get('file_path')
        file_type = template.get('file_type', 'docx')
        
        # Create preview filenames
        preview_filename = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000)}"
        preview_pdf_path = os.path.join(static_folder, 'previews', f"{preview_filename}.pdf")
        preview_word_path = os.path.join(static_folder, 'previews', f"{preview_filename}.docx")
        
        # Clean up old previews
        cleanup_old_previews(static_folder)
        
        if file_type == 'docx':
            print(f"DEBUG: Generating preview with {len(field_mappings)} field mappings")
            print(f"DEBUG: Field mappings: {field_mappings}")
            
            # Generate Word document with replacements using the passed function
            success = generate_word_func(
                template_path, field_mappings, preview_word_path
            )
            
            if success and os.path.exists(preview_word_path) and os.path.getsize(preview_word_path) > 0:
                print(f"DEBUG: Word document generated successfully: {preview_word_path}")
                
                # Try to convert to PDF with retry mechanism
                pdf_success = False
                max_retries = 3
                retry_delay = 1  # seconds
                
                for attempt in range(max_retries):
                    print(f"DEBUG: PDF conversion attempt {attempt + 1}/{max_retries}")
                    
                    # Wait a bit before attempting (except first attempt)
                    if attempt > 0:
                        print(f"DEBUG: Waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        # Increase delay for next attempt
                        retry_delay *= 1.5
                    
                    # Remove old PDF if it exists
                    if os.path.exists(preview_pdf_path):
                        try:
                            os.remove(preview_pdf_path)
                        except:
                            pass
                    
                    # Attempt conversion
                    pdf_success = convert_pdf_func(preview_word_path, preview_pdf_path)
                    
                    if pdf_success and validate_pdf_func(preview_pdf_path):
                        print(f"DEBUG: PDF conversion successful on attempt {attempt + 1}")
                        break
                    else:
                        print(f"DEBUG: PDF conversion failed on attempt {attempt + 1}")
                        # If validation failed and file exists, remove it
                        if os.path.exists(preview_pdf_path):
                            try:
                                os.remove(preview_pdf_path)
                            except:
                                pass
                
                # After all retries, check if PDF was successfully created
                if pdf_success and validate_pdf_func(preview_pdf_path):
                    print(f"DEBUG: Returning PDF preview")
                    return {
                        'success': True,
                        'preview_url': f'/static/previews/{os.path.basename(preview_pdf_path)}',
                        'file_type': 'pdf',
                        'word_path': preview_word_path
                    }
                else:
                    # If PDF conversion fails after all retries, fall back to Word format
                    print(f"DEBUG: PDF conversion failed after {max_retries} attempts, falling back to Word format")
                    return {
                        'success': True,
                        'preview_url': f'/static/previews/{os.path.basename(preview_word_path)}',
                        'file_type': 'word',
                        'message': 'Preview generated as Word document. Click to download.',
                        'word_path': preview_word_path
                    }
            else:
                print(f"DEBUG: Failed to generate Word document")
                return {
                    'success': False,
                    'error': 'Failed to generate preview document'
                }
        else:
            return {
                'success': False,
                'error': 'Unsupported file type'
            }
            
    except Exception as e:
        print(f"Error generating preview: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def create_preview_response(template, field_values, static_folder, generate_word_func, convert_pdf_func, validate_pdf_func):
    """
    Create the preview response for the API
    """
    bold_instances = template.get('fields', [])
    
    print("=" * 60)
    print("DEBUG: Creating preview response")
    print(f"DEBUG: Total bold instances: {len(bold_instances)}")
    print(f"DEBUG: Field values received: {field_values}")
    print("=" * 60)
    
    # Create field mappings with unique instance IDs AND exact run_id AND all_run_indices
    field_mappings = []
    
    # Process each field
    for idx, instance in enumerate(bold_instances):
        field_id = f"field_{idx + 1}"
        
        # Get the value from the field_values
        value = field_values.get(field_id, '')
        
        print(f"DEBUG: Processing field {field_id}: value='{value}'")
        
        # CRITICAL FIX: Don't use strip() - preserve exact text including spaces
        # Only skip if value is None or empty string (but keep spaces)
        if value is not None and value != '':
            # Get the original text from the instance
            original_text = instance.get('text', '')
            run_id = instance.get('run_id')
            all_run_indices = instance.get('all_run_indices', [])
            
            print(f"DEBUG: Instance data - original='{original_text}', run_id={run_id}, all_run_indices={all_run_indices}")
            
            if not run_id and 'paragraph_index' in instance and 'run_index' in instance:
                run_id = f"body:{instance['paragraph_index']}:{instance['run_index']}"
            
            mapping = {
                'instance_id': field_id,
                'field_name': original_text,
                'original_text': original_text,
                'field_value': value,  # Keep the exact value as typed
                'field_index': idx + 1,
                'run_id': run_id,
                'all_run_indices': all_run_indices  # CRITICAL: Pass all run indices
            }
            
            field_mappings.append(mapping)
            print(f"DEBUG: Created mapping for {field_id}: '{original_text}' -> '{value}' (run_id={run_id}, all_run_indices={all_run_indices})")
        else:
            print(f"DEBUG: Skipping field {field_id} - value is empty")
    
    print(f"DEBUG: Total field mappings created: {len(field_mappings)}")
    print("=" * 60)
    
    # Generate the preview document
    result = generate_preview_document(
        template, 
        field_mappings, 
        static_folder,
        generate_word_func,
        convert_pdf_func,
        validate_pdf_func
    )
    
    return result