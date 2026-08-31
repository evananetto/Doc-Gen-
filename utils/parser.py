# utils/parser.py

import os
import re
from docx import Document
from docx.document import Document as _WordDocument
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn
import pdfplumber
import PyPDF2


def clean_extracted_field(field):
    """Clean extracted field name - preserve ALL characters including slashes, hyphens, commas, dots, and numbers"""
    if not field:
        return ""
    # Only remove colons, semicolons, newlines, tabs - keep everything else
    clean = re.sub(r'[:;\n\r\t]+', '', field)
    # Remove multiple spaces
    clean = re.sub(r'\s+', ' ', clean)
    # Strip leading/trailing spaces
    clean = clean.strip()
    # Remove trailing punctuation only (not internal)
    clean = re.sub(r'[,.;:!?]+$', '', clean)
    return clean


# ---------------------------------------------------------------------------
# Document traversal helpers
# ---------------------------------------------------------------------------

def iter_block_items(parent):
    """Yield paragraphs and tables, in document order, for a Document,
    a table cell, or a header/footer object."""
    if isinstance(parent, _WordDocument):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    elif hasattr(parent, '_element'):
        parent_elm = parent._element
    else:
        raise ValueError(f"iter_block_items: unsupported parent type {type(parent)}")

    for child in parent_elm.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


def iter_all_paragraphs(parent):
    """Recursively yield every paragraph, including ones inside (nested) tables."""
    for block in iter_block_items(parent):
        if isinstance(block, Paragraph):
            yield block
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    yield from iter_all_paragraphs(cell)


def is_run_effectively_bold(run, paragraph):
    """Resolve bold the way Word actually renders it."""
    if run.bold is not None:
        return run.bold
    try:
        if run.style and run.style.font and run.style.font.bold is not None:
            return run.style.font.bold
    except Exception:
        pass
    try:
        style = paragraph.style
        while style is not None:
            if style.font and style.font.bold is not None:
                return style.font.bold
            style = style.base_style
    except Exception:
        pass
    return False


def merge_consecutive_bold_runs(paragraph):
    """
    CRITICAL FIX: Merge ALL consecutive bold runs within a paragraph into single continuous text blocks.
    
    When text is bold in Word, it may be split across multiple runs for various reasons:
    - Special characters like '/', '.', ',' can create new runs
    - Spaces can create new runs
    - Formatting changes can create new runs
    
    This function correctly identifies ALL bold text in the paragraph and groups
    ALL consecutive bold runs together into single fields.
    
    Examples:
    - "AGREEMENT OF ASSIGNMENT/AGREEMENT FOR PLEDGING OF FIXED DEPOSIT" → ONE field
    - "Mr.Radhakrishnan P.S" → ONE field
    - "S/o Sankara Pillai" → ONE field
    """
    if not paragraph.runs:
        return []
    
    merged_runs = []
    current_text = ""
    current_run_indices = []
    in_bold_sequence = False
    
    # Iterate through all runs in the paragraph
    for idx, run in enumerate(paragraph.runs):
        is_bold = is_run_effectively_bold(run, paragraph)
        run_text = run.text
        
        if is_bold:
            # This run is bold
            if in_bold_sequence:
                # Continue the existing bold sequence
                current_text += run_text
                current_run_indices.append(idx)
            else:
                # Start a new bold sequence
                in_bold_sequence = True
                current_text = run_text
                current_run_indices = [idx]
        else:
            # This run is NOT bold - end the current bold sequence if any
            if in_bold_sequence and current_text.strip():
                merged_runs.append({
                    'text': current_text,
                    'run_indices': current_run_indices,
                    'start_run_index': current_run_indices[0],
                    'end_run_index': current_run_indices[-1]
                })
            in_bold_sequence = False
            current_text = ""
            current_run_indices = []
    
    # Don't forget the last sequence if it's bold
    if in_bold_sequence and current_text.strip():
        merged_runs.append({
            'text': current_text,
            'run_indices': current_run_indices,
            'start_run_index': current_run_indices[0],
            'end_run_index': current_run_indices[-1]
        })
    
    return merged_runs


# ---------------------------------------------------------------------------
# DOCX extraction - Extract each bold instance separately with position
# ---------------------------------------------------------------------------

def extract_bold_instances_from_docx(file_path):
    """
    Extract EACH bold text instance separately with position info.
    Each occurrence gets its own entry with unique ID.
    Merges ALL consecutive bold runs into single continuous fields.
    """
    bold_instances = []
    instance_counter = 0
    paragraph_counter = 0
    
    try:
        doc = Document(file_path)
        
        print("=" * 60)
        print("DEBUG: Starting document parsing for bold instances")
        print("=" * 60)
        
        def process_paragraphs(paragraphs, location):
            nonlocal instance_counter, paragraph_counter
            
            for paragraph in paragraphs:
                # Skip empty paragraphs
                if not paragraph.text.strip():
                    paragraph_counter += 1
                    continue
                
                # First, check if there are any bold runs at all
                has_bold = False
                for run in paragraph.runs:
                    if is_run_effectively_bold(run, paragraph):
                        has_bold = True
                        break
                
                if not has_bold:
                    paragraph_counter += 1
                    continue
                
                # Merge ALL consecutive bold runs into single text blocks
                merged_bold_runs = merge_consecutive_bold_runs(paragraph)
                
                print(f"DEBUG: Paragraph {paragraph_counter} has {len(paragraph.runs)} runs, merged into {len(merged_bold_runs)} bold blocks")
                
                for merged in merged_bold_runs:
                    # Get the FULL text exactly as it appears
                    original_text = merged['text']
                    text = original_text.strip()
                    
                    # Skip empty or whitespace-only
                    if not text:
                        continue
                    
                    # Clean the text for display (preserves slashes, commas, etc.)
                    clean_text = clean_extracted_field(text)
                    
                    # Skip if cleaning removed everything
                    if not clean_text:
                        continue
                    
                    instance_counter += 1
                    unique_id = f"bold_{instance_counter}"
                    
                    # Use the start run index for run_id
                    run_idx = merged['start_run_index']
                    # IMPORTANT: Use the FIRST run index for the run_id
                    run_id = f"{location}:{paragraph_counter}:{run_idx}"
                    
                    # Store ALL run indices for this field
                    all_run_indices = merged['run_indices']
                    
                    bold_instances.append({
                        'id': unique_id,
                        'text': clean_text,
                        'original_text': original_text,
                        'display_text': clean_text[:50] + '...' if len(clean_text) > 50 else clean_text,
                        'instance_number': instance_counter,
                        'location': location,
                        'paragraph_index': paragraph_counter,
                        'run_index': run_idx,
                        'run_id': run_id,
                        'all_run_indices': all_run_indices,  # Store all run indices for replacement
                        'merged_count': len(all_run_indices),
                        'full_paragraph_text': paragraph.text.strip()
                    })
                    
                    print(f"DEBUG: Extracted bold instance #{instance_counter}: '{clean_text[:50]}' at {location}:{paragraph_counter}:{run_idx} (merged {len(all_run_indices)} runs)")
                
                paragraph_counter += 1
        
        # Process body + all tables
        body_paragraphs = list(iter_all_paragraphs(doc))
        process_paragraphs(body_paragraphs, "body")
        
        # Process headers and footers
        for section_idx, section in enumerate(doc.sections):
            header_paragraphs = list(iter_all_paragraphs(section.header))
            process_paragraphs(header_paragraphs, f"header_{section_idx}")
            
            footer_paragraphs = list(iter_all_paragraphs(section.footer))
            process_paragraphs(footer_paragraphs, f"footer_{section_idx}")
        
        print("\n" + "=" * 60)
        print(f"DEBUG: Total bold instances extracted: {len(bold_instances)}")
        for i, inst in enumerate(bold_instances[:10], 1):
            print(f"  {i}. '{inst['text'][:50]}' (run_id: {inst['run_id']}, merged: {inst['merged_count']} runs)")
        print("=" * 60)
        
        return bold_instances
        
    except Exception as e:
        print(f"Error parsing docx: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_fields_from_docx(file_path):
    """Legacy function - returns just the text values for backward compatibility."""
    instances = extract_bold_instances_from_docx(file_path)
    return [inst['text'] for inst in instances]


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_fields_from_pdf_pdfplumber(file_path):
    """Extract bold/colored text from PDF using pdfplumber"""
    fields = []
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            all_caps_pattern = r'\b([A-Z][A-Z\s\.\-]{2,})\b'
            all_caps_matches = re.findall(all_caps_pattern, full_text)
            for match in all_caps_matches:
                clean_field = clean_extracted_field(match)
                if clean_field and len(clean_field) > 1:
                    fields.append(clean_field)
            
            lines = full_text.split('\n')
            for line in lines:
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        field_name = parts[0].strip()
                        if 1 < len(field_name) < 50:
                            clean_field = re.sub(r'[^\w\s\.\-]', '', field_name)
                            clean_field = clean_extracted_field(clean_field)
                            if clean_field:
                                fields.append(clean_field)
        
        seen = set()
        unique_fields = []
        for field in fields:
            if field and field not in seen:
                seen.add(field)
                unique_fields.append(field)
        
        return unique_fields
    except Exception as e:
        print(f"Error parsing pdf with pdfplumber: {e}")
        return []


def extract_fields_from_pdf_fallback(file_path):
    """Fallback method using PyPDF2"""
    fields = []
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            full_text = ""
            
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            all_caps = re.findall(r'\b([A-Z][A-Z\s\.\-]{2,})\b', full_text)
            for word in all_caps:
                clean_word = clean_extracted_field(word)
                if clean_word and len(clean_word) > 1:
                    fields.append(clean_word)
            
            lines = full_text.split('\n')
            for line in lines:
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        field_name = parts[0].strip()
                        if 1 < len(field_name) < 50:
                            clean_field = re.sub(r'[^\w\s\.\-]', '', field_name)
                            clean_field = clean_extracted_field(clean_field)
                            if clean_field:
                                fields.append(clean_field)
        
        seen = set()
        unique_fields = []
        for field in fields:
            if field and field not in seen:
                seen.add(field)
                unique_fields.append(field)
        
        return unique_fields
    except Exception as e:
        print(f"Error parsing pdf with fallback: {e}")
        return []


def extract_fields_from_pdf(file_path):
    """Main PDF extraction function"""
    fields = extract_fields_from_pdf_pdfplumber(file_path)
    
    if not fields:
        print("No fields found with pdfplumber, trying fallback...")
        fields = extract_fields_from_pdf_fallback(file_path)
    
    skip_words = ['the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 'are', 'was', 'were',
                  'has', 'had', 'can', 'will', 'would', 'could', 'should', 'may', 'might', 'must']
    
    cleaned_fields = []
    for field in fields:
        if field.lower() in skip_words:
            continue
        cleaned_fields.append(field)
    
    return cleaned_fields


def parse_template(file_path, file_type):
    """Main function to parse template and extract fields."""
    if file_type == 'docx':
        return extract_bold_instances_from_docx(file_path)
    elif file_type == 'pdf':
        return extract_fields_from_pdf(file_path)
    else:
        return []