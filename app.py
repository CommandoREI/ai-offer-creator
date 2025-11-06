from flask import Flask, render_template_string, request, jsonify, send_file
from flask_cors import CORS
import os
from datetime import datetime
import json
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io

app = Flask(__name__)
CORS(app)

# Initialize OpenAI client
client = OpenAI()

# Strategy definitions with explanations
STRATEGIES = {
    'cash': {
        'name': 'All Cash',
        'description': 'Traditional cash purchase - fastest and simplest',
        'when_to_use': 'High motivation, needs speed, wants certainty',
        'pros': ['Fastest close', 'No financing contingencies', 'Simplest transaction'],
        'cons': ['Requires capital', 'Usually lowest price', 'Limited flexibility']
    },
    'subject_to': {
        'name': 'Subject-To (Take Over Payments)',
        'description': 'Take over existing mortgage payments without formal assumption',
        'when_to_use': 'Seller has equity, good loan terms, needs debt relief',
        'pros': ['Low cash needed', 'Leverage existing financing', 'Can offer higher price'],
        'cons': ['Due-on-sale risk', 'Requires seller trust', 'More complex']
    },
    'lease_option': {
        'name': 'Lease Option',
        'description': 'Lease property with option to purchase later',
        'when_to_use': 'Low cash available, seller flexible on timing, needs income',
        'pros': ['Minimal cash needed', 'Control without ownership', 'Time to improve property'],
        'cons': ['No immediate ownership', 'Monthly payments', 'Seller retains title']
    },
    'seller_financing': {
        'name': 'Seller Financing',
        'description': 'Seller acts as the bank and carries a note',
        'when_to_use': 'Seller owns free and clear, wants income stream, flexible',
        'pros': ['Creative terms possible', 'Lower down payment', 'Seller gets interest'],
        'cons': ['Seller retains lien', 'Monthly payments', 'Requires seller trust']
    },
    'hybrid': {
        'name': 'Hybrid (Cash + Terms)',
        'description': 'Combination of cash and creative financing',
        'when_to_use': 'Moderate motivation, some cash available, needs flexibility',
        'pros': ['Balanced approach', 'Flexible structure', 'Appeals to more sellers'],
        'cons': ['More complex', 'Requires negotiation', 'Medium cash needed']
    }
}

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/strategies')
def get_strategies():
    """Return available strategies with explanations"""
    return jsonify(STRATEGIES)

@app.route('/api/generate-offers', methods=['POST'])
def generate_offers():
    """Generate two strategic offers based on user inputs"""
    try:
        data = request.json
        
        # Extract inputs
        strategy1 = data.get('strategy1')
        strategy2 = data.get('strategy2')
        weight1 = int(data.get('weight1', 50))
        weight2 = int(data.get('weight2', 50))
        
        # Property data
        property_data = {
            'arv': float(data.get('arv', 0)),
            'repairs': float(data.get('repairs', 0)),
            'mortgage_balance': float(data.get('mortgage_balance', 0)),
            'monthly_payment': float(data.get('monthly_payment', 0)),
            'condition': data.get('condition', 5)
        }
        
        # Seller data
        seller_data = {
            'motivation_score': int(data.get('motivation_score', 5)),
            'pain_point': data.get('pain_point', ''),
            'timeline': data.get('timeline', ''),
            'cash_needed': float(data.get('cash_needed', 0)),
            'priorities': data.get('priorities', [])
        }
        
        # Investor criteria
        investor_data = {
            'max_offer_percent': float(data.get('max_offer_percent', 70)),
            'min_profit': float(data.get('min_profit', 20000)),
            'available_cash': float(data.get('available_cash', 10000)),
            'exit_strategy': data.get('exit_strategy', 'flip')
        }
        
        # Advanced mode settings
        advanced_mode = data.get('advanced_mode', False)
        advanced_settings = data.get('advanced_settings', {})
        
        # Generate offers using AI
        offers = generate_strategic_offers(
            strategy1, strategy2, weight1, weight2,
            property_data, seller_data, investor_data,
            advanced_mode, advanced_settings
        )
        
        return jsonify(offers)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_strategic_offers(strategy1, strategy2, weight1, weight2,
                              property_data, seller_data, investor_data,
                              advanced_mode, advanced_settings):
    """Use AI to generate two strategic offers"""
    
    # Build prompt for AI
    prompt = f"""You are an expert real estate investor creating strategic offer scenarios.

PROPERTY DETAILS:
- ARV (After Repair Value): ${property_data['arv']:,.0f}
- Estimated Repairs: ${property_data['repairs']:,.0f}
- Current Mortgage: ${property_data['mortgage_balance']:,.0f}
- Monthly Payment: ${property_data['monthly_payment']:,.0f}
- Property Condition: {property_data['condition']}/10

SELLER SITUATION:
- Motivation Score: {seller_data['motivation_score']}/10
- Primary Pain Point: {seller_data['pain_point']}
- Timeline: {seller_data['timeline']}
- Cash Needed at Closing: ${seller_data['cash_needed']:,.0f}
- Priorities: {', '.join(seller_data['priorities'])}

INVESTOR CRITERIA:
- Max Offer: {investor_data['max_offer_percent']}% of ARV
- Minimum Profit Target: ${investor_data['min_profit']:,.0f}
- Available Cash: ${investor_data['available_cash']:,.0f}
- Exit Strategy: {investor_data['exit_strategy']}

OFFER STRATEGIES:
Offer A: {STRATEGIES[strategy1]['name']} (Weight: {weight1}% - {'MORE attractive' if weight1 > 50 else 'LESS attractive' if weight1 < 50 else 'EQUALLY attractive'})
Offer B: {STRATEGIES[strategy2]['name']} (Weight: {weight2}% - {'MORE attractive' if weight2 > 50 else 'LESS attractive' if weight2 < 50 else 'EQUALLY attractive'})

INSTRUCTIONS:
Generate TWO complete offer scenarios. The weighting determines relative attractiveness:
- Higher weight (>50%) = More attractive terms for seller (higher price, more cash, faster close, better terms)
- Lower weight (<50%) = Less attractive but still legitimate (lower price, less cash, longer timeline)
- Equal weight (50/50) = Both equally attractive with different benefits

For each offer, provide:
1. Purchase price (realistic based on ARV and strategy)
2. Cash at closing (what seller receives after mortgage payoff)
3. Payment structure (if applicable)
4. Closing timeline
5. Key terms and conditions
6. 3-4 seller benefits (why this works for them)
7. Presentation script (how to verbally present this offer)
8. Strategic notes for investor (negotiation tips, fallback positions)

Return ONLY valid JSON in this exact format:
{{
  "offer_a": {{
    "strategy": "{strategy1}",
    "headline": "Compelling headline for this offer",
    "purchase_price": 100000,
    "cash_at_closing": 5000,
    "payment_structure": "Description of payment terms",
    "timeline_days": 14,
    "terms": ["Term 1", "Term 2", "Term 3"],
    "seller_benefits": ["Benefit 1", "Benefit 2", "Benefit 3"],
    "presentation_script": "Mr. Seller, this option...",
    "investor_notes": "Strategic guidance for investor"
  }},
  "offer_b": {{
    "strategy": "{strategy2}",
    "headline": "Compelling headline for this offer",
    "purchase_price": 95000,
    "cash_at_closing": 3000,
    "payment_structure": "Description of payment terms",
    "timeline_days": 10,
    "terms": ["Term 1", "Term 2", "Term 3"],
    "seller_benefits": ["Benefit 1", "Benefit 2", "Benefit 3"],
    "presentation_script": "Mr. Seller, this option...",
    "investor_notes": "Strategic guidance for investor"
  }},
  "comparison_intro": "Brief intro script for presenting both offers together",
  "closing_question": "Question to ask after presenting both offers"
}}"""

    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are an expert real estate investor and negotiation strategist. Generate realistic, strategic offer scenarios in valid JSON format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    
    # Parse response
    result = json.loads(response.choices[0].message.content)
    
    # Add metadata
    result['generated_at'] = datetime.now().isoformat()
    result['property_arv'] = property_data['arv']
    result['seller_motivation'] = seller_data['motivation_score']
    
    return result

@app.route('/api/export-pdf', methods=['POST'])
def export_pdf():
    """Generate PDF export of offers"""
    try:
        data = request.json
        offers = data.get('offers')
        format_type = data.get('format', 'branded')  # 'branded' or 'pro'
        
        # Generate PDF
        pdf_buffer = generate_pdf(offers, format_type)
        
        # Return PDF
        filename = f"offer_comparison_{'pro' if format_type == 'pro' else 'branded'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_pdf(offers, format_type):
    """Generate PDF document"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2e7d32') if format_type == 'branded' else colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2e7d32') if format_type == 'branded' else colors.HexColor('#333333'),
        spaceAfter=12
    )
    
    # Title
    if format_type == 'branded':
        story.append(Paragraph("AI Offer Creator - Real Estate Commando", title_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
    else:
        story.append(Paragraph("Property Offer Comparison", title_style))
        story.append(Spacer(1, 0.2*inch))
    
    # Offer A
    story.append(Paragraph(f"Option A: {offers['offer_a']['headline']}", heading_style))
    
    offer_a_data = [
        ['Purchase Price:', f"${offers['offer_a']['purchase_price']:,.0f}"],
        ['Cash at Closing:', f"${offers['offer_a']['cash_at_closing']:,.0f}"],
        ['Payment Structure:', offers['offer_a']['payment_structure']],
        ['Closing Timeline:', f"{offers['offer_a']['timeline_days']} days"],
    ]
    
    table_a = Table(offer_a_data, colWidths=[2*inch, 4*inch])
    table_a.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    
    story.append(table_a)
    story.append(Spacer(1, 0.2*inch))
    
    # Benefits A
    story.append(Paragraph("Why This Works:", styles['Heading3']))
    for benefit in offers['offer_a']['seller_benefits']:
        story.append(Paragraph(f"• {benefit}", styles['Normal']))
    
    story.append(Spacer(1, 0.4*inch))
    
    # Offer B
    story.append(Paragraph(f"Option B: {offers['offer_b']['headline']}", heading_style))
    
    offer_b_data = [
        ['Purchase Price:', f"${offers['offer_b']['purchase_price']:,.0f}"],
        ['Cash at Closing:', f"${offers['offer_b']['cash_at_closing']:,.0f}"],
        ['Payment Structure:', offers['offer_b']['payment_structure']],
        ['Closing Timeline:', f"{offers['offer_b']['timeline_days']} days"],
    ]
    
    table_b = Table(offer_b_data, colWidths=[2*inch, 4*inch])
    table_b.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    
    story.append(table_b)
    story.append(Spacer(1, 0.2*inch))
    
    # Benefits B
    story.append(Paragraph("Why This Works:", styles['Heading3']))
    for benefit in offers['offer_b']['seller_benefits']:
        story.append(Paragraph(f"• {benefit}", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer

# HTML Template will be added in next file
HTML_TEMPLATE = '<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>AI Offer Creator - Real Estate Commando</title>\n    <style>\n        * {\n            margin: 0;\n            padding: 0;\n            box-sizing: border-box;\n        }\n\n        body {\n            font-family: \'Segoe UI\', Tahoma, Geneva, Verdana, sans-serif;\n            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);\n            color: #e0e0e0;\n            min-height: 100vh;\n            padding: 20px;\n        }\n\n        .container {\n            max-width: 1200px;\n            margin: 0 auto;\n        }\n\n        .header {\n            background: linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%);\n            padding: 30px;\n            border-radius: 10px;\n            margin-bottom: 30px;\n            box-shadow: 0 4px 6px rgba(0,0,0,0.3);\n            border: 2px solid #4caf50;\n        }\n\n        .header h1 {\n            color: #ffffff;\n            font-size: 32px;\n            margin-bottom: 10px;\n            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);\n        }\n\n        .header p {\n            color: #c8e6c9;\n            font-size: 16px;\n        }\n\n        .mode-toggle {\n            background: #2d2d2d;\n            padding: 20px;\n            border-radius: 10px;\n            margin-bottom: 20px;\n            border: 2px solid #4caf50;\n            display: flex;\n            justify-content: space-between;\n            align-items: center;\n        }\n\n        .mode-buttons {\n            display: flex;\n            gap: 10px;\n        }\n\n        .mode-btn {\n            padding: 12px 24px;\n            border: 2px solid #4caf50;\n            background: #1a1a1a;\n            color: #4caf50;\n            cursor: pointer;\n            border-radius: 5px;\n            font-size: 14px;\n            font-weight: bold;\n            transition: all 0.3s;\n        }\n\n        .mode-btn.active {\n            background: #4caf50;\n            color: #1a1a1a;\n        }\n\n        .mode-btn:hover {\n            transform: translateY(-2px);\n            box-shadow: 0 4px 8px rgba(76, 175, 80, 0.3);\n        }\n\n        .card {\n            background: #2d2d2d;\n            border-radius: 10px;\n            padding: 25px;\n            margin-bottom: 20px;\n            border: 2px solid #4caf50;\n            box-shadow: 0 4px 6px rgba(0,0,0,0.3);\n        }\n\n        .card h2 {\n            color: #4caf50;\n            margin-bottom: 20px;\n            font-size: 24px;\n            border-bottom: 2px solid #4caf50;\n            padding-bottom: 10px;\n        }\n\n        .strategy-selector {\n            display: grid;\n            grid-template-columns: 1fr 1fr;\n            gap: 20px;\n            margin-bottom: 20px;\n        }\n\n        .offer-config {\n            background: #1a1a1a;\n            padding: 20px;\n            border-radius: 8px;\n            border: 2px solid #4caf50;\n        }\n\n        .offer-config h3 {\n            color: #4caf50;\n            margin-bottom: 15px;\n            font-size: 18px;\n        }\n\n        .form-group {\n            margin-bottom: 20px;\n        }\n\n        .form-group label {\n            display: block;\n            color: #4caf50;\n            margin-bottom: 8px;\n            font-weight: bold;\n            font-size: 14px;\n        }\n\n        .form-group select,\n        .form-group input[type="number"],\n        .form-group input[type="text"],\n        .form-group textarea {\n            width: 100%;\n            padding: 12px;\n            background: #2d2d2d;\n            border: 2px solid #4caf50;\n            border-radius: 5px;\n            color: #e0e0e0;\n            font-size: 14px;\n        }\n\n        .form-group select:focus,\n        .form-group input:focus,\n        .form-group textarea:focus {\n            outline: none;\n            border-color: #66bb6a;\n            box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.2);\n        }\n\n        .weight-slider {\n            margin-top: 15px;\n        }\n\n        .weight-display {\n            display: flex;\n            justify-content: space-between;\n            align-items: center;\n            margin-bottom: 10px;\n        }\n\n        .weight-value {\n            font-size: 24px;\n            font-weight: bold;\n            color: #4caf50;\n        }\n\n        .weight-label {\n            font-size: 12px;\n            color: #9e9e9e;\n        }\n\n        input[type="range"] {\n            width: 100%;\n            height: 8px;\n            border-radius: 5px;\n            background: #1a1a1a;\n            outline: none;\n            -webkit-appearance: none;\n        }\n\n        input[type="range"]::-webkit-slider-thumb {\n            -webkit-appearance: none;\n            appearance: none;\n            width: 20px;\n            height: 20px;\n            border-radius: 50%;\n            background: #4caf50;\n            cursor: pointer;\n            box-shadow: 0 2px 4px rgba(0,0,0,0.3);\n        }\n\n        input[type="range"]::-moz-range-thumb {\n            width: 20px;\n            height: 20px;\n            border-radius: 50%;\n            background: #4caf50;\n            cursor: pointer;\n            box-shadow: 0 2px 4px rgba(0,0,0,0.3);\n        }\n\n        .presets {\n            display: flex;\n            gap: 10px;\n            flex-wrap: wrap;\n            margin-top: 15px;\n        }\n\n        .preset-btn {\n            padding: 10px 16px;\n            background: #1a1a1a;\n            border: 2px solid #4caf50;\n            color: #4caf50;\n            border-radius: 5px;\n            cursor: pointer;\n            font-size: 13px;\n            transition: all 0.3s;\n        }\n\n        .preset-btn:hover {\n            background: #4caf50;\n            color: #1a1a1a;\n        }\n\n        .strategy-info {\n            background: #1a1a1a;\n            padding: 15px;\n            border-radius: 5px;\n            margin-top: 10px;\n            border-left: 4px solid #4caf50;\n        }\n\n        .strategy-info h4 {\n            color: #4caf50;\n            margin-bottom: 8px;\n            font-size: 14px;\n        }\n\n        .strategy-info p {\n            color: #9e9e9e;\n            font-size: 13px;\n            line-height: 1.5;\n        }\n\n        .strategy-info ul {\n            margin-top: 8px;\n            padding-left: 20px;\n        }\n\n        .strategy-info li {\n            color: #9e9e9e;\n            font-size: 12px;\n            margin-bottom: 4px;\n        }\n\n        .btn-primary {\n            background: linear-gradient(135deg, #4caf50 0%, #2e7d32 100%);\n            color: white;\n            padding: 16px 32px;\n            border: none;\n            border-radius: 8px;\n            font-size: 18px;\n            font-weight: bold;\n            cursor: pointer;\n            width: 100%;\n            transition: all 0.3s;\n            box-shadow: 0 4px 6px rgba(0,0,0,0.3);\n        }\n\n        .btn-primary:hover {\n            transform: translateY(-2px);\n            box-shadow: 0 6px 12px rgba(76, 175, 80, 0.4);\n        }\n\n        .btn-primary:disabled {\n            opacity: 0.5;\n            cursor: not-allowed;\n        }\n\n        .results {\n            display: none;\n        }\n\n        .results.show {\n            display: block;\n        }\n\n        .offer-comparison {\n            display: grid;\n            grid-template-columns: 1fr 1fr;\n            gap: 20px;\n            margin-top: 20px;\n        }\n\n        .offer-card {\n            background: #1a1a1a;\n            padding: 25px;\n            border-radius: 8px;\n            border: 2px solid #4caf50;\n        }\n\n        .offer-card h3 {\n            color: #4caf50;\n            margin-bottom: 15px;\n            font-size: 20px;\n        }\n\n        .offer-detail {\n            margin-bottom: 15px;\n            padding-bottom: 15px;\n            border-bottom: 1px solid #3d3d3d;\n        }\n\n        .offer-detail:last-child {\n            border-bottom: none;\n        }\n\n        .offer-detail-label {\n            color: #9e9e9e;\n            font-size: 12px;\n            margin-bottom: 5px;\n        }\n\n        .offer-detail-value {\n            color: #e0e0e0;\n            font-size: 16px;\n            font-weight: bold;\n        }\n\n        .benefits-list {\n            margin-top: 15px;\n        }\n\n        .benefits-list h4 {\n            color: #4caf50;\n            margin-bottom: 10px;\n            font-size: 14px;\n        }\n\n        .benefits-list ul {\n            list-style: none;\n            padding: 0;\n        }\n\n        .benefits-list li {\n            color: #e0e0e0;\n            padding: 8px 0;\n            padding-left: 25px;\n            position: relative;\n            font-size: 14px;\n        }\n\n        .benefits-list li:before {\n            content: "✓";\n            color: #4caf50;\n            font-weight: bold;\n            position: absolute;\n            left: 0;\n        }\n\n        .presentation-script {\n            background: #1a1a1a;\n            padding: 20px;\n            border-radius: 8px;\n            margin-top: 20px;\n            border-left: 4px solid #4caf50;\n        }\n\n        .presentation-script h3 {\n            color: #4caf50;\n            margin-bottom: 15px;\n        }\n\n        .presentation-script p {\n            color: #e0e0e0;\n            line-height: 1.8;\n            margin-bottom: 15px;\n        }\n\n        .export-buttons {\n            display: flex;\n            gap: 15px;\n            margin-top: 20px;\n        }\n\n        .btn-export {\n            flex: 1;\n            padding: 14px 24px;\n            border: 2px solid #4caf50;\n            background: #2d2d2d;\n            color: #4caf50;\n            border-radius: 8px;\n            font-size: 16px;\n            font-weight: bold;\n            cursor: pointer;\n            transition: all 0.3s;\n        }\n\n        .btn-export:hover {\n            background: #4caf50;\n            color: #1a1a1a;\n        }\n\n        .loading {\n            text-align: center;\n            padding: 40px;\n            color: #4caf50;\n            font-size: 18px;\n        }\n\n        .spinner {\n            border: 4px solid #2d2d2d;\n            border-top: 4px solid #4caf50;\n            border-radius: 50%;\n            width: 50px;\n            height: 50px;\n            animation: spin 1s linear infinite;\n            margin: 20px auto;\n        }\n\n        @keyframes spin {\n            0% { transform: rotate(0deg); }\n            100% { transform: rotate(360deg); }\n        }\n\n        .advanced-section {\n            display: none;\n        }\n\n        .advanced-section.show {\n            display: block;\n        }\n\n        @media (max-width: 768px) {\n            .strategy-selector,\n            .offer-comparison {\n                grid-template-columns: 1fr;\n            }\n        }\n    </style>\n</head>\n<body>\n    <div class="container">\n        <div class="header">\n            <h1>🎯 AI Offer Creator</h1>\n            <p>Generate strategic offer scenarios with AI-powered positioning</p>\n        </div>\n\n        <div class="mode-toggle">\n            <div>\n                <strong style="color: #4caf50;">Mode:</strong>\n                <span id="modeDescription" style="color: #9e9e9e; margin-left: 10px;">Quick strategy selection</span>\n            </div>\n            <div class="mode-buttons">\n                <button class="mode-btn active" onclick="setMode(\'simple\')">🟢 Simple Mode</button>\n                <button class="mode-btn" onclick="setMode(\'advanced\')">🔵 Advanced Mode</button>\n            </div>\n        </div>\n\n        <div id="inputSection">\n            <!-- Strategy Selection -->\n            <div class="card">\n                <h2>1️⃣ Select Offer Strategies</h2>\n                \n                <div class="form-group">\n                    <label>Quick Presets:</label>\n                    <div class="presets">\n                        <button class="preset-btn" onclick="applyPreset(\'sub2_vs_cash\')">Subject-To vs Cash</button>\n                        <button class="preset-btn" onclick="applyPreset(\'two_sub2\')">Two Subject-To Variations</button>\n                        <button class="preset-btn" onclick="applyPreset(\'creative\')">Creative Options</button>\n                        <button class="preset-btn" onclick="applyPreset(\'stacked\')">Stacked Deck (80/20)</button>\n                    </div>\n                </div>\n\n                <div class="strategy-selector">\n                    <!-- Offer A -->\n                    <div class="offer-config">\n                        <h3>Offer A</h3>\n                        <div class="form-group">\n                            <label>Strategy:</label>\n                            <select id="strategy1" onchange="updateStrategyInfo(\'strategy1\', \'info1\')">\n                                <option value="cash">All Cash</option>\n                                <option value="subject_to" selected>Subject-To (Take Over Payments)</option>\n                                <option value="lease_option">Lease Option</option>\n                                <option value="seller_financing">Seller Financing</option>\n                                <option value="hybrid">Hybrid (Cash + Terms)</option>\n                            </select>\n                        </div>\n                        \n                        <div class="weight-slider">\n                            <div class="weight-display">\n                                <span class="weight-label">Attractiveness:</span>\n                                <span class="weight-value" id="weight1Display">70%</span>\n                            </div>\n                            <input type="range" id="weight1" min="0" max="100" value="70" \n                                   oninput="updateWeight(\'weight1\', \'weight1Display\', \'weight2\', \'weight2Display\')">\n                            <div style="display: flex; justify-content: space-between; margin-top: 5px;">\n                                <span style="font-size: 11px; color: #9e9e9e;">Less Attractive</span>\n                                <span style="font-size: 11px; color: #9e9e9e;">More Attractive</span>\n                            </div>\n                        </div>\n\n                        <div id="info1" class="strategy-info"></div>\n                    </div>\n\n                    <!-- Offer B -->\n                    <div class="offer-config">\n                        <h3>Offer B</h3>\n                        <div class="form-group">\n                            <label>Strategy:</label>\n                            <select id="strategy2" onchange="updateStrategyInfo(\'strategy2\', \'info2\')">\n                                <option value="cash" selected>All Cash</option>\n                                <option value="subject_to">Subject-To (Take Over Payments)</option>\n                                <option value="lease_option">Lease Option</option>\n                                <option value="seller_financing">Seller Financing</option>\n                                <option value="hybrid">Hybrid (Cash + Terms)</option>\n                            </select>\n                        </div>\n                        \n                        <div class="weight-slider">\n                            <div class="weight-display">\n                                <span class="weight-label">Attractiveness:</span>\n                                <span class="weight-value" id="weight2Display">30%</span>\n                            </div>\n                            <input type="range" id="weight2" min="0" max="100" value="30" \n                                   oninput="updateWeight(\'weight2\', \'weight2Display\', \'weight1\', \'weight1Display\')">\n                            <div style="display: flex; justify-content: space-between; margin-top: 5px;">\n                                <span style="font-size: 11px; color: #9e9e9e;">Less Attractive</span>\n                                <span style="font-size: 11px; color: #9e9e9e;">More Attractive</span>\n                            </div>\n                        </div>\n\n                        <div id="info2" class="strategy-info"></div>\n                    </div>\n                </div>\n            </div>\n\n            <!-- Property Data -->\n            <div class="card">\n                <h2>2️⃣ Property Information</h2>\n                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">\n                    <div class="form-group">\n                        <label>ARV (After Repair Value):</label>\n                        <input type="number" id="arv" placeholder="150000" value="150000">\n                    </div>\n                    <div class="form-group">\n                        <label>Estimated Repairs:</label>\n                        <input type="number" id="repairs" placeholder="30000" value="30000">\n                    </div>\n                    <div class="form-group">\n                        <label>Current Mortgage Balance:</label>\n                        <input type="number" id="mortgage_balance" placeholder="95000" value="95000">\n                    </div>\n                    <div class="form-group">\n                        <label>Monthly Mortgage Payment:</label>\n                        <input type="number" id="monthly_payment" placeholder="850" value="850">\n                    </div>\n                    <div class="form-group">\n                        <label>Property Condition (1-10):</label>\n                        <input type="number" id="condition" min="1" max="10" placeholder="5" value="5">\n                    </div>\n                </div>\n            </div>\n\n            <!-- Seller Data -->\n            <div class="card">\n                <h2>3️⃣ Seller Situation</h2>\n                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">\n                    <div class="form-group">\n                        <label>Motivation Score (1-10):</label>\n                        <input type="number" id="motivation_score" min="1" max="10" placeholder="8" value="8">\n                    </div>\n                    <div class="form-group">\n                        <label>Primary Pain Point:</label>\n                        <select id="pain_point">\n                            <option value="financial_distress">Financial Distress</option>\n                            <option value="time_pressure">Time Pressure</option>\n                            <option value="property_condition">Property Condition</option>\n                            <option value="distance">Geographic Distance</option>\n                            <option value="inheritance">Inheritance/Estate</option>\n                            <option value="divorce">Divorce</option>\n                        </select>\n                    </div>\n                    <div class="form-group">\n                        <label>Timeline:</label>\n                        <select id="timeline">\n                            <option value="immediate">Immediate (Days)</option>\n                            <option value="30_days">30 Days</option>\n                            <option value="60_days">60 Days</option>\n                            <option value="90_days">90+ Days</option>\n                            <option value="flexible">Flexible</option>\n                        </select>\n                    </div>\n                    <div class="form-group">\n                        <label>Cash Needed at Closing:</label>\n                        <input type="number" id="cash_needed" placeholder="5000" value="5000">\n                    </div>\n                </div>\n            </div>\n\n            <!-- Investor Criteria -->\n            <div class="card">\n                <h2>4️⃣ Your Investment Criteria</h2>\n                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">\n                    <div class="form-group">\n                        <label>Max Offer (% of ARV):</label>\n                        <input type="number" id="max_offer_percent" min="50" max="100" placeholder="70" value="70">\n                    </div>\n                    <div class="form-group">\n                        <label>Minimum Profit Target:</label>\n                        <input type="number" id="min_profit" placeholder="20000" value="20000">\n                    </div>\n                    <div class="form-group">\n                        <label>Available Cash:</label>\n                        <input type="number" id="available_cash" placeholder="10000" value="10000">\n                    </div>\n                    <div class="form-group">\n                        <label>Exit Strategy:</label>\n                        <select id="exit_strategy">\n                            <option value="flip">Flip</option>\n                            <option value="wholesale">Wholesale</option>\n                            <option value="rental">Rental/Hold</option>\n                            <option value="brrrr">BRRRR</option>\n                        </select>\n                    </div>\n                </div>\n            </div>\n\n            <!-- Advanced Settings -->\n            <div class="card advanced-section" id="advancedSettings">\n                <h2>⚙️ Advanced Settings</h2>\n                <p style="color: #9e9e9e; margin-bottom: 20px;">Fine-tune specific terms and conditions</p>\n                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">\n                    <div class="form-group">\n                        <label>Force Specific Price Range:</label>\n                        <input type="text" id="price_range" placeholder="e.g., 85000-95000">\n                    </div>\n                    <div class="form-group">\n                        <label>Required Closing Timeline:</label>\n                        <input type="text" id="required_timeline" placeholder="e.g., 7-14 days">\n                    </div>\n                </div>\n            </div>\n\n            <button class="btn-primary" onclick="generateOffers()">\n                🚀 Generate Strategic Offers\n            </button>\n        </div>\n\n        <!-- Results Section -->\n        <div id="resultsSection" class="results">\n            <div class="card">\n                <h2>📊 Your Strategic Offer Scenarios</h2>\n                \n                <div class="presentation-script" id="introScript"></div>\n\n                <div class="offer-comparison" id="offerComparison"></div>\n\n                <div class="presentation-script" id="closingScript"></div>\n\n                <div class="export-buttons">\n                    <button class="btn-export" onclick="exportPDF(\'branded\')">\n                        📄 Export Branded PDF\n                    </button>\n                    <button class="btn-export" onclick="exportPDF(\'pro\')">\n                        ⭐ Export Pro PDF (Unbranded)\n                    </button>\n                    <button class="btn-export" onclick="resetForm()">\n                        🔄 Create New Offers\n                    </button>\n                </div>\n            </div>\n        </div>\n\n        <div id="loadingSection" class="loading" style="display: none;">\n            <div class="spinner"></div>\n            <p>Generating strategic offers with AI...</p>\n        </div>\n    </div>\n\n    <script>\n        let currentMode = \'simple\';\n        let strategies = {};\n        let currentOffers = null;\n\n        // Load strategies on page load\n        fetch(\'/api/strategies\')\n            .then(res => res.json())\n            .then(data => {\n                strategies = data;\n                updateStrategyInfo(\'strategy1\', \'info1\');\n                updateStrategyInfo(\'strategy2\', \'info2\');\n            });\n\n        function setMode(mode) {\n            currentMode = mode;\n            const buttons = document.querySelectorAll(\'.mode-btn\');\n            buttons.forEach(btn => btn.classList.remove(\'active\'));\n            event.target.classList.add(\'active\');\n            \n            const advancedSection = document.getElementById(\'advancedSettings\');\n            const modeDescription = document.getElementById(\'modeDescription\');\n            \n            if (mode === \'advanced\') {\n                advancedSection.classList.add(\'show\');\n                modeDescription.textContent = \'Full control over terms and conditions\';\n            } else {\n                advancedSection.classList.remove(\'show\');\n                modeDescription.textContent = \'Quick strategy selection\';\n            }\n        }\n\n        function updateWeight(sliderId, displayId, otherSliderId, otherDisplayId) {\n            const value = document.getElementById(sliderId).value;\n            document.getElementById(displayId).textContent = value + \'%\';\n            \n            // Auto-adjust other slider to maintain 100% total\n            const otherValue = 100 - parseInt(value);\n            document.getElementById(otherSliderId).value = otherValue;\n            document.getElementById(otherDisplayId).textContent = otherValue + \'%\';\n        }\n\n        function updateStrategyInfo(strategySelectId, infoId) {\n            const strategy = document.getElementById(strategySelectId).value;\n            const info = strategies[strategy];\n            \n            if (info) {\n                const html = `\n                    <h4>${info.name}</h4>\n                    <p><strong>When to use:</strong> ${info.when_to_use}</p>\n                    <p><strong>Pros:</strong></p>\n                    <ul>\n                        ${info.pros.map(pro => `<li>${pro}</li>`).join(\'\')}\n                    </ul>\n                `;\n                document.getElementById(infoId).innerHTML = html;\n            }\n        }\n\n        function applyPreset(preset) {\n            switch(preset) {\n                case \'sub2_vs_cash\':\n                    document.getElementById(\'strategy1\').value = \'subject_to\';\n                    document.getElementById(\'strategy2\').value = \'cash\';\n                    document.getElementById(\'weight1\').value = 70;\n                    document.getElementById(\'weight2\').value = 30;\n                    break;\n                case \'two_sub2\':\n                    document.getElementById(\'strategy1\').value = \'subject_to\';\n                    document.getElementById(\'strategy2\').value = \'subject_to\';\n                    document.getElementById(\'weight1\').value = 50;\n                    document.getElementById(\'weight2\').value = 50;\n                    break;\n                case \'creative\':\n                    document.getElementById(\'strategy1\').value = \'lease_option\';\n                    document.getElementById(\'strategy2\').value = \'seller_financing\';\n                    document.getElementById(\'weight1\').value = 50;\n                    document.getElementById(\'weight2\').value = 50;\n                    break;\n                case \'stacked\':\n                    document.getElementById(\'strategy1\').value = \'subject_to\';\n                    document.getElementById(\'strategy2\').value = \'cash\';\n                    document.getElementById(\'weight1\').value = 80;\n                    document.getElementById(\'weight2\').value = 20;\n                    break;\n            }\n            \n            updateWeight(\'weight1\', \'weight1Display\', \'weight2\', \'weight2Display\');\n            updateStrategyInfo(\'strategy1\', \'info1\');\n            updateStrategyInfo(\'strategy2\', \'info2\');\n        }\n\n        async function generateOffers() {\n            // Show loading\n            document.getElementById(\'inputSection\').style.display = \'none\';\n            document.getElementById(\'loadingSection\').style.display = \'block\';\n            \n            // Collect data\n            const data = {\n                strategy1: document.getElementById(\'strategy1\').value,\n                strategy2: document.getElementById(\'strategy2\').value,\n                weight1: document.getElementById(\'weight1\').value,\n                weight2: document.getElementById(\'weight2\').value,\n                arv: document.getElementById(\'arv\').value,\n                repairs: document.getElementById(\'repairs\').value,\n                mortgage_balance: document.getElementById(\'mortgage_balance\').value,\n                monthly_payment: document.getElementById(\'monthly_payment\').value,\n                condition: document.getElementById(\'condition\').value,\n                motivation_score: document.getElementById(\'motivation_score\').value,\n                pain_point: document.getElementById(\'pain_point\').value,\n                timeline: document.getElementById(\'timeline\').value,\n                cash_needed: document.getElementById(\'cash_needed\').value,\n                max_offer_percent: document.getElementById(\'max_offer_percent\').value,\n                min_profit: document.getElementById(\'min_profit\').value,\n                available_cash: document.getElementById(\'available_cash\').value,\n                exit_strategy: document.getElementById(\'exit_strategy\').value,\n                advanced_mode: currentMode === \'advanced\',\n                advanced_settings: {}\n            };\n            \n            try {\n                const response = await fetch(\'/api/generate-offers\', {\n                    method: \'POST\',\n                    headers: {\'Content-Type\': \'application/json\'},\n                    body: JSON.stringify(data)\n                });\n                \n                const offers = await response.json();\n                currentOffers = offers;\n                displayOffers(offers);\n                \n                // Show results\n                document.getElementById(\'loadingSection\').style.display = \'none\';\n                document.getElementById(\'resultsSection\').classList.add(\'show\');\n                \n            } catch (error) {\n                alert(\'Error generating offers: \' + error.message);\n                document.getElementById(\'loadingSection\').style.display = \'none\';\n                document.getElementById(\'inputSection\').style.display = \'block\';\n            }\n        }\n\n        function displayOffers(offers) {\n            // Intro script\n            document.getElementById(\'introScript\').innerHTML = `\n                <h3>📋 Presentation Introduction</h3>\n                <p>${offers.comparison_intro}</p>\n            `;\n            \n            // Offer cards\n            const comparisonHtml = `\n                ${createOfferCard(offers.offer_a, \'A\')}\n                ${createOfferCard(offers.offer_b, \'B\')}\n            `;\n            document.getElementById(\'offerComparison\').innerHTML = comparisonHtml;\n            \n            // Closing script\n            document.getElementById(\'closingScript\').innerHTML = `\n                <h3>❓ Closing Question</h3>\n                <p><strong>"${offers.closing_question}"</strong></p>\n            `;\n        }\n\n        function createOfferCard(offer, label) {\n            return `\n                <div class="offer-card">\n                    <h3>Option ${label}: ${offer.headline}</h3>\n                    \n                    <div class="offer-detail">\n                        <div class="offer-detail-label">Purchase Price</div>\n                        <div class="offer-detail-value">$${offer.purchase_price.toLocaleString()}</div>\n                    </div>\n                    \n                    <div class="offer-detail">\n                        <div class="offer-detail-label">Cash at Closing</div>\n                        <div class="offer-detail-value">$${offer.cash_at_closing.toLocaleString()}</div>\n                    </div>\n                    \n                    <div class="offer-detail">\n                        <div class="offer-detail-label">Payment Structure</div>\n                        <div class="offer-detail-value">${offer.payment_structure}</div>\n                    </div>\n                    \n                    <div class="offer-detail">\n                        <div class="offer-detail-label">Closing Timeline</div>\n                        <div class="offer-detail-value">${offer.timeline_days} days</div>\n                    </div>\n                    \n                    <div class="benefits-list">\n                        <h4>Why This Works for You:</h4>\n                        <ul>\n                            ${offer.seller_benefits.map(b => `<li>${b}</li>`).join(\'\')}\n                        </ul>\n                    </div>\n                    \n                    <div class="presentation-script" style="margin-top: 20px;">\n                        <h4>Presentation Script:</h4>\n                        <p style="font-size: 13px;">${offer.presentation_script}</p>\n                    </div>\n                    \n                    <div style="background: #0d0d0d; padding: 15px; border-radius: 5px; margin-top: 15px;">\n                        <h4 style="color: #ff9800; margin-bottom: 8px; font-size: 13px;">📝 Investor Notes:</h4>\n                        <p style="font-size: 12px; color: #9e9e9e;">${offer.investor_notes}</p>\n                    </div>\n                </div>\n            `;\n        }\n\n        async function exportPDF(format) {\n            try {\n                const response = await fetch(\'/api/export-pdf\', {\n                    method: \'POST\',\n                    headers: {\'Content-Type\': \'application/json\'},\n                    body: JSON.stringify({\n                        offers: currentOffers,\n                        format: format\n                    })\n                });\n                \n                const blob = await response.blob();\n                const url = window.URL.createObjectURL(blob);\n                const a = document.createElement(\'a\');\n                a.href = url;\n                a.download = `offer_comparison_${format}_${new Date().toISOString().split(\'T\')[0]}.pdf`;\n                document.body.appendChild(a);\n                a.click();\n                window.URL.revokeObjectURL(url);\n                document.body.removeChild(a);\n                \n            } catch (error) {\n                alert(\'Error exporting PDF: \' + error.message);\n            }\n        }\n\n        function resetForm() {\n            document.getElementById(\'resultsSection\').classList.remove(\'show\');\n            document.getElementById(\'inputSection\').style.display = \'block\';\n            window.scrollTo(0, 0);\n        }\n    </script>\n</body>\n</html>\n'  # Will be populated

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
