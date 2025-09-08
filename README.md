# GrantWriter AI

AI tool to:
- Draft grant applications aligned to pasted criteria
- Score sections with strengths/gaps
- Export DOCX/Markdown with council branding
- Save/Load projects
- Discover grants (RSS/pages), extract deadline/amount, rank relevance, and send Slack alerts

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add your OPENAI_API_KEY and branding
streamlit run app.py
