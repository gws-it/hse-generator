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
- Likelihood (L): 1=Rare, 2=Unlikely, 3=Possible, 4=Likely, 5=Almost certain
- RPN = S × L | Low:1-4 | Medium:5-9 | High:10-16 | Critical:17-25

Always output ONLY valid JSON with no markdown, no commentary."""


def extract_project_details(mos_text: str) -> dict:
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

Use empty string or empty array when not found. Limit ra_members to 3 names.

METHOD STATEMENT:
{mos_text[:6000]}"""
        }]
    )
    return json.loads(_clean_json(response.content[0].text))


def _generate_ra(mos_text: str, project_details: dict, few_shot_examples: list = None,
                 feedback: str = None, previous_ra: dict = None) -> dict:
    """Generate only the RA section."""

    few_shot_block = ""
    if few_shot_examples:
        few_shot_block = "\n\n--- REFERENCE EXAMPLES ---\n"
        for ex in few_shot_examples[:1]:
            ra_ex = ex.get("ra", {})
            snippet = json.dumps(ra_ex, indent=2)[:2000]
            few_shot_block += f"\nPast {ex.get('project_type','')} RA example:\n{snippet}\n"
        few_shot_block += "--- END ---\n"

    feedback_block = ""
    if feedback and previous_ra:
        feedback_block = f"""
--- USER FEEDBACK ---
{feedback}

PREVIOUS RA (fix the issues above):
{json.dumps(previous_ra, indent=2)[:4000]}
--- END FEEDBACK ---
"""

    prompt = f"""Generate a complete Risk Assessment (RA) for ALL activities in this Method Statement.

PROJECT: {project_details.get('project_name','')} | Type: {project_details.get('project_type','')} | Location: {project_details.get('location','')}
{few_shot_block}{feedback_block}
METHOD STATEMENT (activities section):
{mos_text[:8000]}

Output ONLY this JSON (no markdown):
{{
  "activities": [
    {{
      "sn": "1.1",
      "sub_activity": "Activity name",
      "hazard": "Specific hazard for this activity",
      "possible_injury": "Possible injury/damage/environmental impact",
      "existing_controls": {{
        "elimination": "measure or NA",
        "substitution": "measure or NA",
        "engineering": "engineering controls",
        "administrative": "administrative controls including permits",
        "ppe": "required PPE"
      }},
      "initial_s": 4,
      "initial_l": 2,
      "initial_rpn": 8,
      "additional_controls": {{
        "elimination": "NA",
        "substitution": "NA",
        "engineering": "additional measure or NA",
        "administrative": "additional measure or NA",
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
}}

Include ALL activities from the MOS. Last activity must be SGSecure / Emergency Preparedness."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_clean_json(response.content[0].text))


def _generate_swp(mos_text: str, project_details: dict, ra_activities: list,
                  feedback: str = None, previous_swp: dict = None) -> dict:
    """Generate only the SWP section."""

    feedback_block = ""
    if feedback and previous_swp:
        feedback_block = f"""
--- USER FEEDBACK ---
{feedback}

PREVIOUS SWP (fix the issues above):
{json.dumps(previous_swp, indent=2)[:4000]}
--- END FEEDBACK ---
"""

    activity_names = [a.get("sub_activity", "") for a in ra_activities]

    prompt = f"""Generate a Safe Work Procedure (SWP) for this project.

PROJECT: {project_details.get('project_name','')} | Type: {project_details.get('project_type','')} | Location: {project_details.get('location','')}
{feedback_block}
ACTIVITIES TO COVER:
{json.dumps(activity_names, indent=2)}

METHOD STATEMENT:
{mos_text[:6000]}

Output ONLY this JSON (no markdown):
{{
  "purpose": "Clear purpose statement for this SWP",
  "location": "{project_details.get('location','')}",
  "activities": [
    {{
      "name": "Activity name matching RA",
      "steps": [
        "Specific actionable step 1 for workers",
        "Step 2",
        "Continue all steps needed"
      ]
    }}
  ]
}}

Include an activity for every item in the activities list above. Keep each step concise and worker-facing."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_clean_json(response.content[0].text))


def generate_ra_swp(
    mos_text: str,
    project_details: dict,
    few_shot_examples: list = None,
    feedback: str = None,
    previous_output: dict = None,
) -> dict:
    """Generate RA and SWP in two separate calls to avoid token limit truncation."""

    prev_ra = previous_output.get("ra") if previous_output else None
    prev_swp = previous_output.get("swp") if previous_output else None

    ra = _generate_ra(mos_text, project_details, few_shot_examples, feedback, prev_ra)
    swp = _generate_swp(mos_text, project_details, ra.get("activities", []), feedback, prev_swp)

    return {
        "project_type": project_details.get("project_type", ""),
        "ra": ra,
        "swp": swp,
    }


def _clean_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{") or part.startswith("["):
                text = part
                break
    # Remove any trailing content after the last closing brace
    last_brace = text.rfind("}")
    if last_brace != -1:
        text = text[:last_brace + 1]
    return text.strip()
