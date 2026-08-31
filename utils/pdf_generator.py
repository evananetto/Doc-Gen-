# utils/pdf_generator.py

import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

def generate_pdf(template_data, form_values, output_path):
    """
    Generate a PDF using reportlab
    """
    try:
        # Create the PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.HexColor('#1a1a1a')
        )
        
        heading_style = ParagraphStyle(
            'HeadingStyle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#4f46e5'),
            spaceAfter=12
        )
        
        field_label_style = ParagraphStyle(
            'FieldLabelStyle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#555555'),
            fontName='Helvetica-Bold'
        )
        
        field_value_style = ParagraphStyle(
            'FieldValueStyle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#1a1a1a')
        )
        
        normal_style = ParagraphStyle(
            'NormalStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333')
        )
        
        # Build content
        content = []
        
        # === HEADER ===
        content.append(Paragraph("DOCUMENT GENERATOR", ParagraphStyle(
            'HeaderTitle',
            fontSize=16,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#4f46e5'),
            alignment=TA_CENTER
        )))
        content.append(Spacer(1, 0.2*inch))
        
        # === TEMPLATE CONTENT ===
        template_name = template_data.get('name', 'Document')
        fields = template_data.get('fields', [])
        
        # Title
        content.append(Paragraph(template_name, title_style))
        content.append(Spacer(1, 0.1*inch))
        
        # Date
        current_date = datetime.now().strftime('%B %d, %Y')
        content.append(Paragraph(f"Generated on: {current_date}", normal_style))
        content.append(Spacer(1, 0.2*inch))
        
        # Divider line
        content.append(Paragraph("_" * 80, normal_style))
        content.append(Spacer(1, 0.2*inch))
        
        # Fields and values
        if fields:
            for field in fields:
                value = form_values.get(field, '')
                
                # Create a table for each field
                data = [
                    [Paragraph(f"{field}:", field_label_style), 
                     Paragraph(value if value else '__________________', field_value_style)]
                ]
                
                table = Table(data, colWidths=[2.5*inch, 3.5*inch])
                table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMLINE', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
                ]))
                content.append(table)
                content.append(Spacer(1, 0.02*inch))
        
        # === WITNESS SECTION ===
        content.append(Spacer(1, 0.3*inch))
        content.append(Paragraph("Witnesses", heading_style))
        content.append(Spacer(1, 0.1*inch))
        
        witness_data = [
            ["1. Name and address:", "_________________________________________"],
            ["2. Name and address:", "_________________________________________"]
        ]
        
        witness_table = Table(witness_data, colWidths=[2.5*inch, 3.5*inch])
        witness_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
        ]))
        content.append(witness_table)
        
        # === SIGNATURE BLOCK ===
        content.append(Spacer(1, 0.5*inch))
        
        signature_data = [
            ["", ""],
            ["", ""],
            ["_________________________", "_________________________"],
            ["Signature", "Date"]
        ]
        
        signature_table = Table(signature_data, colWidths=[3*inch, 3*inch])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0, 2), (0, 2), 'CENTER'),
            ('ALIGN', (1, 2), (1, 2), 'CENTER'),
            ('ALIGN', (0, 3), (0, 3), 'CENTER'),
            ('ALIGN', (1, 3), (1, 3), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        content.append(signature_table)
        
        # === FOOTER ===
        content.append(Spacer(1, 0.5*inch))
        content.append(Paragraph(
            "Generated by DocGen - Document Generation Platform",
            normal_style
        ))
        
        # Build the PDF
        doc.build(content)
        return True
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
        return False