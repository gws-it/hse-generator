import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior HSE (Health, Safety & Environment) professional with 20+ years of experience in Singapore construction, green infrastructure, and landscape projects. You specialize in writing Risk Assessments (RA) and Safe Work Procedures (SWP) that comply with Singapore's Workplace Safety and Health (WSH) Act and MOM regulations.

Project types and their typical hazard profiles:
- Green Wall: Working at height on facade (up to 25m), structural steel installation, crane/lifting operations, welding, chemical anchor drilling, planter box installation, irrigation piping, planting works
- Green Roof: Working at height on roof, waterproofing works, structural loading, slippery surfaces, heat stress, crane lifts, drainage installation
- Construction: Excavation, heavy machinery, formwork, concrete works, electrical installation, confined space, noise/dust/vibration
- Landscape: Manual handling, power tools (chainsaw, brush cutter), sun/heat exposure, chemical fertilizers/pesticides, traffic management, earthworks

Risk Rating (Singapore Standard):
- Severity (S): 1=Negligible, 2=Minor injury/first aid, 3=Major injury/hospitalisation, 4=Permanent disability, 5=Fatality
- Likelihood (L): 1=Rare (<1/year), 2=Unlikely (1/year), 3=Possible (monthly), 4=Likely (weekly), 5=Almost certain (daily)
- RPN = S × L | Low: 1-4 | Medium: 5-9 | High: 10-16 | Critical: 17-25

Control hierarchy (use in this order):
1. Elimination - remove the hazard entirely
2. Substitution - replace with something safer
3. Engineering - physical controls (guards, barriers, ventilation)
4. Administrative - procedures, training, supervision, permits
5. PPE - last resort

Always output ONLY valid JSON with no markdown, no commentary."""


def extract_project_details(mos_text: str) -> dict:
    """Use Claude to extract and prefill project details from MOS."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system='You extract structured project information from construction Method Statements. Output ONLY valid JSON, no markdown.',
        messages=[{
            "role": "user",
            "content": f"""Extract project details from this Method Statement. Return this JSON exactly:
{{
  "project_name": "full project name",
  "project_type": "one of: Green Wall, Green Roof, Construction, Landscape",
  "location": "site address or project location",
  "ra_leader": "name of person who prepares/leads RA",
  "approved_by": "approver name",
  "ra_members": ["member1", "member2", "member3"],
  "reference_no": "document reference number or empty string",
  "company": "sub-contractor or company name",
  "client": "client/employer name",
  "assessment_date": "date in DD MMM YYYY format or empty string"
}}

Use empty string "" or empty array [] when information is not found. For ra_members, include up to 3 names.

METHOD STATEMENT TEXT:
{mos_text[:8000]}"""
        }]
    )
    text = _clean_json(response.content[0].text)
    return json.loads(text)


def generate_ra_swp(
    mos_text: str,
    project_details: dict,
    few_shot_examples: list = None,
    feedback: str = None,
    previous_output: dict = None,
) -> dict:
    """Generate RA and SWP. If feedback provided, regenerate with corrections."""

    few_shot_block = ""
    if few_shot_examples:
        few_shot_block = "\n\n--- REFERENCE EXAMPLES FROM PAST PROJECTS ---\n"
        for ex in few_shot_examples[:2]:
            snippet = json.dumps(ex, indent=2)[:3000]
            few_shot_block += f"\nPast {ex.get('project_type', '')} example:\n{snippet}\n"
        few_shot_block += "--- END EXAMPLES ---\n"

    feedback_block = ""
    if feedback and previous_output:
        prev_snippet = json.dumps(previous_output, indent=2)[:6000]
        feedback_block = f"""
--- USER FEEDBACK ON PREVIOUS GENERATION ---
{feedback}

PREVIOUS GENERATION (fix the issues above):
{prev_snippet}
--- END FEEDBACK ---
"""

    prompt = f"""Generate a complete, detailed Risk Assessment (RA) and Safe Work Procedure (SWP) based on this Method Statement.

PROJECT DETAILS:
- Project Name: {project_details.get('project_name', '')}
- Project Type: {project_details.get('project_type', '')}
- Location: {project_details.get('location', '')}
- Company: {project_details.get('company', 'GWS LIVINGART PTE LTD')}
- Client: {project_details.get('client', '')}
{few_shot_block}
{feedback_block}

METHOD STATEMENT:
{mos_text[:10000]}

Output this JSON structure exactly — include ALL activities from the MOS, be thorough and specific:

{{
  "project_type": "{project_details.get('project_type', '')}",
  "ra": {{
    "activities": [
      {{
        "sn": "1.1",
        "sub_activity": "Activity name",
        "hazard": "Specific hazard description relevant to this activity",
        "possible_injury": "Possible injury / ill-health / property damage / environmental impact",
        "existing_controls": {{
          "elimination": "Specific elimination measure or NA",
          "substitution": "Specific substitution measure or NA",
          "engineering": "Specific engineering controls",
          "administrative": "Specific administrative controls including permits, training, supervision",
          "ppe": "Required PPE for this activity"
        }},
        "initial_s": 4,
        "initial_l": 2,
        "initial_rpn": 8,
        "additional_controls": {{
          "elimination": "NA",
          "substitution": "NA",
          "engineering": "Additional engineering measure or NA",
          "administrative": "Additional administrative measure or NA",
          "ppe": "NA"
        }},
        "residual_s": 3,
        "residual_l": 1,
        "residual_rpn": 3,
        "implementation_person": "Site Supervisor",
        "due_date": "On-going",
        "remarks": ""
      }}
    ]
  }},
  "swp": {{
    "purpose": "Clear purpose statement describing what this SWP covers and its scope",
    "location": "{project_details.get('location', '')}",
    "activities": [
      {{
        "name": "Activity name matching RA",
        "steps": [
          "Specific step 1 — actionable instruction for workers",
          "Specific step 2",
          "Continue for all steps needed"
        ]
      }}
    ]
  }}
}}

Requirements:
- Include every activity from the MOS work sequence
- Always end with SGSecure / Emergency Preparedness as the last activity
- Each activity should have 3-6 specific hazards addressed
- SWP steps must be worker-facing, clear, and actionable
- Risk ratings must be realistic and follow Singapore WSH standards
- Initial RPN should be higher than residual RPN (controls must reduce risk)"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _clean_json(response.content[0].text)
    return json.loads(text)


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
