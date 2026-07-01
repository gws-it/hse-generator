import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior HSE (Health, Safety & Environment) professional with 20+ years of experience in Singapore construction, green infrastructure, and landscape projects. You specialize in writing Risk Assessments (RA) and Safe Work Procedures (SWP) that comply with Singapore's Workplace Safety and Health (WSH) Act and MOM regulations.

Project types and their typical hazard profiles:
- Green Wall: Working at height on facade (up to 25m), structural steel installation, crane/lifting operations, welding, chemical anchor drilling, planter box installation, irrigation piping, planting works
- Green Roof: Working at height on roof, waterproofing works, structural loading, slippery surfaces, heat stress, crane lifts, drainage installation
- Construction: Excavation, heavy machinery, formwork, concrete works, electrical installation, confined space, noise/dust/vibration
- Landscape: Manual handling, power tools, sun/heat exposure, chemical fertilizers/pesticides, traffic management, earthworks

Risk Rating (Singapore Standard):
- Severity (S): 1=Negligible, 2=Minor/first aid, 3=Major/hospitalisation, 4=Permanent disability, 5=Fatality
- Likelihood (L): 1=Rare, 2=Unlikely, 3=Possible, 4=Likely, 5=Almost certain
- RPN = S x L | Low:1-4 | Medium:5-9 | High:10-16 | Critical:17-25"""

# ── Tool schemas ───────────────────────────────────────────────────────────

RA_TOOL = {
    "name": "submit_risk_assessment",
    "description": "Submit the completed Risk Assessment for all activities",
    "input_schema": {
        "type": "object",
        "properties": {
            "activities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sn":               {"type": "string"},
                        "sub_activity":     {"type": "string"},
                        "hazard":           {"type": "string"},
                        "possible_injury":  {"type": "string"},
                        "existing_controls": {
                            "type": "object",
                            "properties": {
                                "elimination":    {"type": "string"},
                                "substitution":   {"type": "string"},
                                "engineering":    {"type": "string"},
                                "administrative": {"type": "string"},
                                "ppe":            {"type": "string"},
                            },
                            "required": ["elimination","substitution","engineering","administrative","ppe"]
                        },
                        "initial_s":   {"type": "integer"},
                        "initial_l":   {"type": "integer"},
                        "initial_rpn": {"type": "integer"},
                        "additional_controls": {
                            "type": "object",
                            "properties": {
                                "elimination":    {"type": "string"},
                                "substitution":   {"type": "string"},
                                "engineering":    {"type": "string"},
                                "administrative": {"type": "string"},
                                "ppe":            {"type": "string"},
                            },
                            "required": ["elimination","substitution","engineering","administrative","ppe"]
                        },
                        "residual_s":   {"type": "integer"},
                        "residual_l":   {"type": "integer"},
                        "residual_rpn": {"type": "integer"},
                        "implementation_person": {"type": "string"},
                        "due_date":   {"type": "string"},
                        "remarks":    {"type": "string"},
                    },
                    "required": ["sn","sub_activity","hazard","possible_injury",
                                 "existing_controls","initial_s","initial_l","initial_rpn",
                                 "additional_controls","residual_s","residual_l","residual_rpn",
                                 "implementation_person","due_date","remarks"]
                }
            }
        },
        "required": ["activities"]
    }
}

SWP_TOOL = {
    "name": "submit_safe_work_procedure",
    "description": "Submit the completed Safe Work Procedure",
    "input_schema": {
        "type": "object",
        "properties": {
            "purpose":  {"type": "string"},
            "location": {"type": "string"},
            "activities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":  {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["name", "steps"]
                }
            }
        },
        "required": ["purpose", "location", "activities"]
    }
}

EXTRACT_TOOL = {
    "name": "submit_project_details",
    "description": "Submit extracted project details from the Method Statement",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_name":    {"type": "string"},
            "project_type":    {"type": "string", "enum": ["Green Wall","Green Roof","Construction","Landscape"]},
            "location":        {"type": "string"},
            "ra_leader":       {"type": "string"},
            "approved_by":     {"type": "string"},
            "ra_members":      {"type": "array", "items": {"type": "string"}},
            "reference_no":    {"type": "string"},
            "company":         {"type": "string"},
            "client":          {"type": "string"},
            "assessment_date": {"type": "string"},
        },
        "required": ["project_name","project_type","location","ra_leader","approved_by",
                     "ra_members","reference_no","company","client","assessment_date"]
    }
}


def _call_tool(system: str, user_msg: str, tool: dict, max_tokens: int = 8192) -> dict:
    """Call Claude with tool_use forced — guarantees valid structured output."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("No tool_use block in Claude response")


# ── Public functions ───────────────────────────────────────────────────────

def extract_project_details(mos_text: str) -> dict:
    return _call_tool(
        system="You extract structured project information from construction Method Statements.",
        user_msg=f"""Extract project details from this Method Statement.
For project_type choose the best match from: Green Wall, Green Roof, Construction, Landscape.
Use empty string when a field is not found. Limit ra_members to max 3 names.

METHOD STATEMENT:
{mos_text[:6000]}""",
        tool=EXTRACT_TOOL,
        max_tokens=800,
    )


def _build_ra_prompt(mos_text: str, project_details: dict,
                     few_shot_examples: list = None,
                     feedback: str = None, previous_ra: dict = None) -> str:
    few_shot_block = ""
    if few_shot_examples:
        ex = few_shot_examples[0]
        parts = []
        if ex.get("mos_text"):
            parts.append(f"EXAMPLE MOS:\n{ex['mos_text'][:1000]}")
        if ex.get("ra_text"):
            parts.append(f"EXAMPLE RA STRUCTURE:\n{ex['ra_text'][:1500]}")
        if parts:
            few_shot_block = (
                f"\n\n--- REFERENCE EXAMPLE ({ex.get('label','')}) ---\n"
                + "\n\n".join(parts)
                + "\n--- END REFERENCE ---\n"
            )

    # Only include previous RA as context if it actually has activities
    feedback_block = ""
    prev_activities = (previous_ra or {}).get("activities", [])
    if feedback and prev_activities:
        feedback_block = (
            f"\n\nUSER FEEDBACK TO FIX:\n{feedback}\n\n"
            f"PREVIOUS RA (fix the issues described above):\n"
            f"{json.dumps(previous_ra, indent=2)[:3000]}\n"
        )
    elif feedback:
        feedback_block = f"\n\nUSER FEEDBACK: {feedback}\n"

    return f"""Generate a complete Risk Assessment for EVERY work activity in this Method Statement.
You MUST populate the activities array — do not return an empty list.

PROJECT: {project_details.get('project_name', '')}
Type: {project_details.get('project_type', '')}
Location: {project_details.get('location', '')}
{few_shot_block}{feedback_block}
METHOD STATEMENT:
{mos_text[:8000]}

Rules:
- activities array must NOT be empty
- Include every distinct work activity from the MOS
- Last entry must be SGSecure / Emergency Preparedness
- initial_rpn must be > residual_rpn
- Be specific — name actual hazards, actual equipment, actual injuries"""


def _generate_ra(mos_text: str, project_details: dict, few_shot_examples: list = None,
                 feedback: str = None, previous_ra: dict = None) -> dict:

    prompt = _build_ra_prompt(mos_text, project_details, few_shot_examples, feedback, previous_ra)
    result = _call_tool(system=SYSTEM_PROMPT, user_msg=prompt, tool=RA_TOOL, max_tokens=8192)

    # Retry once with a simpler prompt if Claude returned empty activities
    if not result.get("activities"):
        print("[WARNING] RA returned empty activities — retrying with simplified prompt")
        simple_prompt = f"""Generate a Risk Assessment for this project. The activities array MUST be filled in.

PROJECT: {project_details.get('project_name', '')} ({project_details.get('project_type', '')})

METHOD STATEMENT SUMMARY:
{mos_text[:5000]}

Fill in at least 10 activities covering the work described above. Do not return an empty activities list."""
        result = _call_tool(system=SYSTEM_PROMPT, user_msg=simple_prompt, tool=RA_TOOL, max_tokens=8192)

    if not result.get("activities"):
        raise ValueError("AI returned no activities after retry. Please try again.")

    return result


def _generate_swp(mos_text: str, project_details: dict, ra_activities: list,
                  few_shot_examples: list = None,
                  feedback: str = None, previous_swp: dict = None) -> dict:

    swp_template_block = ""
    if few_shot_examples:
        ex = few_shot_examples[0] if isinstance(few_shot_examples, list) else None
        if ex and ex.get("swp_text"):
            swp_template_block = f"\n\n--- TEMPLATE EXAMPLE ---\nEXAMPLE SWP OUTPUT:\n{ex['swp_text'][:2000]}\n--- END TEMPLATE ---\n\nMatch the style and detail level of the example above.\n"

    feedback_block = ""
    if feedback and previous_swp:
        feedback_block = f"\n\nUSER FEEDBACK TO FIX:\n{feedback}\n\nPREVIOUS SWP:\n{json.dumps(previous_swp, indent=2)[:3000]}\n"

    activity_names = [a.get("sub_activity", "") for a in ra_activities]

    return _call_tool(
        system=SYSTEM_PROMPT,
        user_msg=f"""Generate a Safe Work Procedure (SWP) for this project.

PROJECT: {project_details.get('project_name','')}
Type: {project_details.get('project_type','')}
Location: {project_details.get('location','')}
{swp_template_block}{feedback_block}
ACTIVITIES TO COVER:
{json.dumps(activity_names, indent=2)}

METHOD STATEMENT:
{mos_text[:5000]}

Instructions:
- Write an activity entry for every item in the activities list
- Steps must be clear, actionable worker instructions
- Keep each step concise (1-2 sentences)""",
        tool=SWP_TOOL,
        max_tokens=8192,
    )


def generate_ra_swp(mos_text: str, project_details: dict, few_shot_examples: list = None,
                    feedback: str = None, previous_output: dict = None) -> dict:

    prev_ra = previous_output.get("ra") if previous_output else None
    prev_swp = previous_output.get("swp") if previous_output else None

    ra = _generate_ra(mos_text, project_details, few_shot_examples, feedback, prev_ra)
    swp = _generate_swp(mos_text, project_details, ra.get("activities", []), few_shot_examples, feedback, prev_swp)

    return {"project_type": project_details.get("project_type", ""), "ra": ra, "swp": swp}
