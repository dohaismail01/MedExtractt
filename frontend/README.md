# MedExtract — Frontend

Small React + TypeScript + Vite UI for the MedExtract API. Paste a clinical
note, submit, and see the structured extraction — chief complaint, symptoms,
diagnoses, medical history, medications, procedures, follow-up — plus a grounded
summary, documentation-based risk/urgency, and ICD-10 code suggestions. Matched
terms are highlighted back in the note.

## Run

The backend must be running first:

```bash
# from the repo root
uvicorn medextract.api.app:app --reload    # http://127.0.0.1:8000
```

Then, in this folder:

```bash
npm install
npm run dev                                 # http://localhost:5173
```

## Configuration

The API base URL defaults to `http://127.0.0.1:8000`. Override it by copying
`.env.example` to `.env` and setting `VITE_API_URL`.

## Notes

- The API returns the project brief's flat schema (plain strings and string
  arrays; no evidence offsets). The UI therefore highlights terms in the note by
  locating each extracted string, so a highlight may be missed if the model's
  term does not appear verbatim.
- `urgency` is reported as `low` / `medium` / `high`, mapped from the backend's
  documentation-based risk assessment.
- This is a demo UI. All output is "for clinician review — not a diagnostic or
  triage tool" (surfaced via `GET /health` and shown as a banner).
