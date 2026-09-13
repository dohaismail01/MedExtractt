Your previous response was not valid against the required schema. This is a
CORRECTION task, not a re-extraction.

Required JSON shape:
{
  "chief_complaint": {"text": "", "evidence": ""} | null,
  "symptoms": [{"text": "", "status": "present|negated|historical|family_history|uncertain", "evidence": ""}],
  "diagnosis": [], "medical_history": [], "procedures": [],
  "medications": [{"name": "", "dose": null, "frequency": null, "duration": null, "evidence": ""}],
  "follow_up": null
}

Validation error(s):
{errors}

Your previous output:
{previous}

Return ONLY a single corrected JSON object. Do not add commentary. Do not invent
new facts to satisfy the schema - keep only facts with evidence spans from the note.
