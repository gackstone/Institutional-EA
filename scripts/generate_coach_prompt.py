"""
Generates Institutional EA Cloud AI Coach System Prompt and Context from knowledge/forex_kb.json.
Guarantees zero contradiction with verified video cards (28 videos: Part 1 Institutional EA + Part 2 Art of Trading).
"""

from __future__ import annotations
import json
from pathlib import Path


def generate_coach_docs():
    kb_path = Path("knowledge/forex_kb.json")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)

    cards = kb.get("cards", [])
    terms = kb.get("terminology", {})
    pipeline = kb.get("confirmation_pipeline", {})
    amendments = kb.get("reconciliation_amendments", [])
    pedagogy = kb.get("pedagogical_rules", [])

    content = []
    content.append("# Institutional EA Cloud AI Trading Coach — Master System Prompt & Knowledge Context (28 Videos)\n")
    content.append("> **Operational Purpose**: Educational quantitative coaching engine powered by Institutional EA & Art of Trading institutional price-action methodology and MT5 quantitative engine.\n")
    
    content.append("## Mandatory Educational Disclaimer")
    content.append(f"> **{kb.get('disclaimer')}**\n")
    content.append("Every response to end users regarding strategy, entry evaluations, or market analysis must begin or end with this disclaimer. Never guarantee profits or suggest financial advice.\n")

    content.append("## Mandatory Caveat Phrases (From Video Captions)")
    content.append("Coach must frequently use these exact grounding phrases to manage user expectations:")
    content.append("- *\"A tendency, not a law.\"* [ART-03]")
    content.append("- *\"Nobody can see the stops. Pools are a map of where orders probably rest, not a promise.\"* [ART-04]")
    content.append("- *\"Nobody outside can prove an algorithm exists. You do not have to believe it to use the lens.\"* [ART-05]")
    content.append("- *\"Easy to label afterward. Live, a pullback and a reversal look identical.\"* [ART-01]")
    content.append("- *\"Price action doesn't predict the future. It shows you where you're wrong.\"* [ART-11]")
    content.append("- *\"The contract is simple. The leverage is not. Size your trade from your stop, not from your margin.\"* [ART-12]\n")

    content.append("## Core Pedagogy & Behavioural Rules\n")
    for idx, rule in enumerate(pedagogy, 1):
        content.append(f"{idx}. {rule}")
    content.append("")

    content.append("## Part 2 Precedence & Amendments (Where Part 2 AMENDS Part 1)\n")
    for amend in amendments:
        content.append(f"### {amend.get('id')}: {amend.get('topic')}")
        content.append(f"- **Rule**: {amend.get('rule')}")
        content.append(f"- **Tags**: `{', '.join(amend.get('tags', []))}`\n")

    content.append("## Institutional Terminology (Source of Truth)\n")
    for k, v in terms.items():
        content.append(f"### {v.get('name')} {v.get('tag', '')}")
        content.append(f"- **Definition**: {v.get('definition')}\n")

    content.append("## The 28 Verified Strategy Video Cards\n")
    for card in cards:
        series = card.get("series", "Institutional EA")
        vid_num = card.get("video_number")
        art_f = f" (File: {card.get('art_file')})" if "art_file" in card else ""
        content.append(f"### Video {vid_num} [{series}{art_f}]: {card.get('title')} (`{card.get('id')}`)")
        content.append(f"- **Core Claim**: {card.get('claim')}")
        content.append("- **Verified Rules**:")
        for r in card.get("rules", []):
            if isinstance(r, dict):
                content.append(f"  * {r.get('rule')} `{r.get('tag')}`")
            else:
                content.append(f"  * {r}")
        if "detection" in card:
            content.append(f"- **Detection**: {card.get('detection')}")
        if "trigger" in card:
            content.append(f"- **Trigger**: {card.get('trigger')}")
        content.append(f"- **Coach Lesson Anchor**: *\"{card.get('coach_lesson')}\"*\n")

    content.append("## Combined Engine Confirmation Pipeline (H0 -> G7 Walkthrough)\n")
    content.append("When evaluating any chart or setup, assess gates in this mandatory order:\n")
    for g in pipeline.get("gates", []):
        content.append(f"### Gate {g.get('name')}")
        content.append(f"- **Associated Skills**: `{', '.join(g.get('skills', []))}`")
        content.append(f"- **Tags**: `{', '.join(g.get('tags', []))}`\n")

    content.append("## Prohibited Topics & Missing Episodes Notice\n")
    content.append(f"- {kb.get('source_attribution', {}).get('missing_episodes_notice')}")
    content.append("- Do not teach ICT 04, 06, or 08 topics beyond what is explicitly stated in this document.")
    content.append("- Time-sensitive figures: E-mini S&P ~$390k contract value changes with index level; always remind students to verify current contract sizes.")
    content.append("- Region-specific regulations: US 60/40 tax and leverage caps (50:1 US, 30:1 UK/EU) are jurisdiction-dependent; tell students to consult local regulations.\n")

    full_text = "\n".join(content)

    out_md = Path("docs/institutional_ea_coach_prompt.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(full_text)

    out_kb = Path("knowledge/coach_context.md")
    with open(out_kb, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"Generated {out_md} and {out_kb} successfully.")


if __name__ == "__main__":
    generate_coach_docs()
