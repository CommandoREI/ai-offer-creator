from flask import Flask, render_template, request, jsonify, send_file
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

# Initialize OpenAI client with timeout
# OpenAI client will automatically use OPENAI_API_KEY from environment
if not os.getenv('OPENAI_API_KEY'):
    print("WARNING: OPENAI_API_KEY environment variable not set!")
client = OpenAI(timeout=60.0)

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
        'name': 'Subject-To (Handle The Mortgage Payments)',
        'description': 'Handle existing mortgage payments until refinance or resale',
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
    return render_template('index.html')

@app.route('/api/strategies')
def get_strategies():
    """Return available strategies with explanations"""
    return jsonify(STRATEGIES)

@app.route('/api/generate', methods=['POST'])
def generate_offers():
    """Generate two strategic offers based on user inputs"""
    try:
        data = request.json
        
        # Extract inputs
        strategy1 = data.get('offer_a_strategy')
        strategy2 = data.get('offer_b_strategy')
        weight1 = int(data.get('offer_a_weight', 50))
        weight2 = int(data.get('offer_b_weight', 50))
        
        # Property data
        property_data = {
            'arv': float(data.get('arv', 0)),
            'repairs': float(data.get('repairs', 0)),
            'mortgage_balance': float(data.get('mortgage_balance', 0)),
            'monthly_payment': float(data.get('monthly_payment', 0)),
            'condition': data.get('condition', 5),
            'arrears': float(data.get('arrears', 0))  # New: back payments/arrears
        }
        
        # Seller data
        seller_data = {
            'motivation_score': int(data.get('motivation', 5)),
            'pain_point': data.get('pain_point', ''),
            'timeline': data.get('timeline', ''),
            'cash_needed': float(data.get('cash_needed', 0)),
            'seller_cash_request': float(data.get('seller_cash_request', 0)),  # New: what seller is asking for
            'priorities': data.get('priorities', [])
        }
        
        # Investor criteria
        # max_offer_percent only applies to cash offers
        investor_data = {
            'max_offer_percent': float(data.get('max_offer_pct', 70)) if data.get('max_offer_pct') else None,
            'min_profit': float(data.get('min_profit', 20000)),
            'available_cash': float(data.get('available_cash', 10000)),
            'exit_strategy': data.get('exit_strategy', 'flip')
        }
        
        # Creative financing terms
        creative_terms = {
            'option_term_months': int(data.get('option_term_months', 36)),  # For Lease Option
            'additional_option_price': float(data.get('additional_option_price', 0)),  # For Lease Option
            'monthly_payment_markup': float(data.get('monthly_payment_markup', 0)),  # For Seller Financing Wrap
            'additional_purchase_price': float(data.get('additional_purchase_price', 0))  # For Seller Financing Wrap
        }
        
        # Advanced mode settings
        advanced_mode = data.get('advanced_mode', False)
        advanced_settings = data.get('advanced_settings', {})
        
        # Generate offers using AI
        offers = generate_strategic_offers(
            strategy1, strategy2, weight1, weight2,
            property_data, seller_data, investor_data,
            creative_terms, advanced_mode, advanced_settings
        )
        
        return jsonify(offers)
        
    except Exception as e:
        print(f"Error in generate_offers: {str(e)}")  # Log to Railway
        import traceback
        traceback.print_exc()  # Print full traceback
        return jsonify({'error': f'Failed to generate offers: {str(e)}'}), 500

def validate_and_fix_cash_offer(offer, property_data):
    """Validate and correct cash offer calculations"""
    purchase_price = offer.get('purchase_price', 0)
    mortgage = property_data['mortgage_balance']
    arrears = property_data['arrears']
    
    # Calculate actual cash at closing (what seller receives after payoffs)
    # This is: Purchase Price - Mortgage Payoff - Arrears - Estimated Closing Costs
    estimated_closing_costs = purchase_price * 0.02  # Estimate 2% for closing costs
    actual_cash_at_closing = purchase_price - mortgage - arrears - estimated_closing_costs
    
    # Update the offer with correct calculation
    offer['cash_at_closing'] = round(actual_cash_at_closing, 0)
    
    # Flag non-viable offers
    if actual_cash_at_closing < 0:
        offer['viability_flag'] = 'NOT VIABLE'
        offer['viability_note'] = f"Seller would need to bring ${abs(round(actual_cash_at_closing, 0)):,.0f} to closing to cover mortgage shortfall"
        
        # Update investor notes to emphasize non-viability
        original_notes = offer.get('investor_notes', '')
        offer['investor_notes'] = f"⚠️ NOT VIABLE: Purchase price (${purchase_price:,.0f}) is less than mortgage + arrears (${mortgage + arrears:,.0f}). Seller would owe ${abs(round(actual_cash_at_closing, 0)):,.0f} at closing. {original_notes}"
        
        # Update presentation script to reflect reality
        offer['presentation_script'] = f"Mr. Seller, while I've calculated a cash offer at ${purchase_price:,.0f}, I need to be transparent with you: after paying off your mortgage (${mortgage:,.0f}) and arrears (${arrears:,.0f}), plus closing costs, you would need to bring approximately ${abs(round(actual_cash_at_closing, 0)):,.0f} to closing. This is why I believe the other offer I'm presenting would work much better for your situation."
    else:
        offer['viability_flag'] = 'VIABLE'
        offer['viability_note'] = f"Seller receives ${round(actual_cash_at_closing, 0):,.0f} cash after all payoffs"

def generate_strategic_offers(strategy1, strategy2, weight1, weight2,
                              property_data, seller_data, investor_data,
                              creative_terms, advanced_mode, advanced_settings):
    """Use AI to generate two strategic offers"""
    
    # Build prompt for AI
    prompt = f"""You are an expert real estate investor creating strategic offer scenarios.

PROPERTY DETAILS:
- ARV (After Repair Value): ${property_data['arv']:,.0f}
- Estimated Repairs: ${property_data['repairs']:,.0f}
- Current Mortgage: ${property_data['mortgage_balance']:,.0f}
- Arrears/Back Payments: ${property_data['arrears']:,.0f}
- Monthly Payment: ${property_data['monthly_payment']:,.0f}
- Property Condition: {property_data['condition']}/10

SELLER SITUATION:
- Motivation Score: {seller_data['motivation_score']}/10
- Primary Pain Point: {seller_data['pain_point']}
- Timeline: {seller_data['timeline']}
- Cash Needed at Closing: ${seller_data['cash_needed']:,.0f}
- Seller's Cash Request: ${seller_data['seller_cash_request']:,.0f}
- Priorities: {', '.join(seller_data['priorities'])}

INVESTOR CRITERIA:
- Max Cash Offer: {investor_data['max_offer_percent']}% of ARV (only applies to all-cash offers)
- Minimum Profit Target: ${investor_data['min_profit']:,.0f}
- Available Cash: ${investor_data['available_cash']:,.0f}
- Exit Strategy: {investor_data['exit_strategy']}

CREATIVE FINANCING TERMS:
- Option Term: {creative_terms['option_term_months']} months (for Lease Option)
- Additional Option Price: ${creative_terms['additional_option_price']:,.0f} (for Lease Option)
- Monthly Payment Markup: ${creative_terms['monthly_payment_markup']:,.0f} (for Seller Financing Wrap)
- Additional Purchase Price: ${creative_terms['additional_purchase_price']:,.0f} (for Seller Financing Wrap)

OFFER STRATEGIES:
Offer A: {STRATEGIES[strategy1]['name']} (Weight: {weight1}% - {'MORE attractive' if weight1 > 50 else 'LESS attractive' if weight1 < 50 else 'EQUALLY attractive'})
Offer B: {STRATEGIES[strategy2]['name']} (Weight: {weight2}% - {'MORE attractive' if weight2 > 50 else 'LESS attractive' if weight2 < 50 else 'EQUALLY attractive'})

INSTRUCTIONS:
Generate TWO complete offer scenarios using the EXACT strategies specified above (Offer A and Offer B).

IMPORTANT: You MUST use the strategy specified for each offer:
- Offer A MUST use the strategy: {STRATEGIES[strategy1]['name']}
- Offer B MUST use the strategy: {STRATEGIES[strategy2]['name']}
- DO NOT auto-generate variations of the same strategy unless BOTH offers use the same strategy

The weighting determines relative attractiveness:
- Higher weight (>50%) = More attractive terms for seller (higher price, more cash, faster close, better terms)
- Lower weight (<50%) = Less attractive but still legitimate (lower price, less cash, longer timeline)
- Equal weight (50/50) = Both equally attractive with different benefits

IMPORTANT CALCULATION RULES:

FOR SUBJECT-TO OFFERS:
- Base amount = Mortgage Balance + Arrears
- Purchase price = Mortgage Balance + Arrears (you're handling the mortgage payments)
- Cash at closing calculation - STRATEGIC VARIATION:
  * If BOTH offers are Subject-To: Create a genuine trade-off using CASH TIMING vs CASH AMOUNT
    
    HIGHER WEIGHT OFFER (More Attractive) - "All Cash Now":
    - Cash amount: 90-100% of seller's cash request
    - Payment timing: 100% paid at closing (ALL UPFRONT)
    - Appeal: Immediate liquidity, instant relief, no waiting
    - Example: Seller requests $5,000 → Offer $4,500-$5,000 all at closing
    
    LOWER WEIGHT OFFER (Less Attractive, But More Total) - "More Money, But Wait":
    - Total cash: 100-120% of seller's cash request (MORE than upfront offer)
    - Payment timing: SPLIT (50% at closing + 50% in 60 days)
    - At closing amount: MUST be LESS than the upfront offer's closing amount
    - Appeal: More total money, but requires patience
    - Example: Seller requests $5,000 → Offer $2,500 at closing + $3,000 in 60 days = $5,500 total
    
    EQUAL WEIGHTS (50/50):
    - BOTH offers get 100% of seller's cash request
    - BOTH paid upfront at closing
    - NO split payment
  
  * If only ONE offer is Subject-To: Use seller's cash request as-is or adjust based on weight

- KEY PSYCHOLOGY: Higher weight = immediate cash (more attractive). Lower weight = more total cash but delayed (creates genuine choice)
- CRITICAL RULE: Split offer's closing payment MUST ALWAYS be LESS than upfront offer's closing payment
- This creates the trade-off: "Take less now, or wait for more"

FOR LEASE OPTION OFFERS:
- Monthly lease payment = Current PITI (mortgage payment)
- Option price = Mortgage Balance + Additional Option Price (from user input)
- Option term = User-specified months (from creative financing terms)
- NO upfront option fee or option payment at closing ($0)
- If BOTH offers are Lease Option: Vary the additional option price (80% and 120%)
- If only ONE offer is Lease Option: Use the additional option price as-is
- Structure: "Lease for $X/month with option to purchase for $Y within Z months"

FOR SELLER FINANCING (WRAP) OFFERS:
- This is a WRAP mortgage - seller keeps existing mortgage, you pay seller, seller pays their mortgage
- Monthly payment to seller = PITI + Monthly Payment Markup (from user input)
- Purchase price = Mortgage Balance + Additional Purchase Price (from user input)
- Interest rate = Same as seller's existing note (seller gets no benefit on rate)
- Term = Same as seller's remaining mortgage term
- If BOTH offers are Seller Financing: Vary the markup and additional price (80% and 120%)
- If only ONE offer is Seller Financing: Use the values as-is
- Structure: "Pay seller $X/month, seller continues paying their mortgage, you control property"

FOR ALL-CASH OFFERS:
- Purchase price = ARV × Max Cash Offer Percentage
- Cash at closing = Purchase price - Mortgage Balance - Arrears
- If cash at closing is negative, this offer is NOT viable (seller would owe money at closing)
- Only present cash offers when the math works for the seller
- Adjust purchase price based on weight (higher weight = higher percentage of ARV)

For each offer, provide:
1. Purchase price (calculated per rules above)
2. Cash at closing (what seller receives after mortgage/arrears payoff)
3. Payment structure (for Subject-To, include split payment details if applicable)
4. Closing timeline
5. Key terms and conditions
6. 3-4 seller benefits (why this works for them)
7. Presentation script (emphasize payment split as flexibility/benefit for Subject-To variation 2)
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

    # Call OpenAI API with error handling
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are an expert real estate investor and negotiation strategist. Generate realistic, strategic offer scenarios in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
            timeout=60.0
        )
    except Exception as api_error:
        print(f"OpenAI API error: {str(api_error)}")
        raise Exception(f"OpenAI API error: {str(api_error)}")
    
    # Parse response
    result = json.loads(response.choices[0].message.content)
    
    # Validate and fix cash offer calculations
    if result.get('offer_a', {}).get('strategy') == 'cash':
        validate_and_fix_cash_offer(result['offer_a'], property_data)
    if result.get('offer_b', {}).get('strategy') == 'cash':
        validate_and_fix_cash_offer(result['offer_b'], property_data)
    
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
    
    # Title (unbranded for both formats)
    story.append(Paragraph("Property Offer Comparison", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Offer A
    story.append(Paragraph(f"Option A: {offers['offer_a']['headline']}", heading_style))
    
    offer_a_data = [
        ['Purchase Price:', f"${offers['offer_a']['purchase_price']:,.0f}"],
        ['Cash at Closing:', f"${offers['offer_a']['cash_at_closing']:,.0f}"],
        ['Payment Structure:', Paragraph(offers['offer_a']['payment_structure'], styles['Normal'])],
        ['Closing Timeline:', f"{offers['offer_a']['timeline_days']} days"],
    ]
    
    table_a = Table(offer_a_data, colWidths=[2*inch, 4.5*inch])
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
        ['Payment Structure:', Paragraph(offers['offer_b']['payment_structure'], styles['Normal'])],
        ['Closing Timeline:', f"{offers['offer_b']['timeline_days']} days"],
    ]
    
    table_b = Table(offer_b_data, colWidths=[2*inch, 4.5*inch])
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
