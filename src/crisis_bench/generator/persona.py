"""User Simulator persona document generation.

Produces a persona.md describing the simulated user for the User
Simulator LLM (Epic 3, Story 3.5).  This file is NOT an agent-readable
memory — it is simulator configuration placed in the scenario root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crisis_bench.models.scenario import AgentIdentity, Contact, PersonProfile

PERSONA_TEMPLATE = """\
# Persona: {name}

You are playing **{name}**, a {occupation} living in New York City.

## Background
- Lives at {home_address} (Upper West Side, Manhattan)
- Works at {office_address} (Empire State Building area)
- Married to {spouse_name}
- Has an AI assistant named **{agent_name}** that runs on his phone and connected devices

## Personality & Communication Style
- Casual, direct, low-key. Doesn't over-explain.
- Types brief messages — often a few words or a short sentence.
- Tech-savvy but treats {agent_name} like a phone assistant, not a novelty.
- Responds quickly to Sarah and family, slower to acquaintances.
- Doesn't use many emojis. Occasional "👍" or "lol" with close contacts.

## Typical Interaction Examples
- "{agent_name}, what's my next meeting?"
- "remind me to call mom tonight"
- "any new messages?"
- "k thanks"

## Key Relationships
{contacts_section}
"""


def generate_persona(
    person: PersonProfile,
    agent_identity: AgentIdentity,
    contacts: list[Contact],
) -> str:
    """Render the persona document using actual scenario data.

    Parameters
    ----------
    person:
        The simulated user's profile.
    agent_identity:
        The AI assistant identity (name, personality).
    contacts:
        The user's contact list for relationship context.

    Returns
    -------
    str
        Rendered persona Markdown content.
    """
    # Build contacts section — highlight key relationships
    key_relationships: dict[str, Contact | None] = {
        "wife": None,
        "mother": None,
        "father": None,
        "brother": None,
        "manager": None,
    }
    for contact in contacts:
        rel = contact.relationship.lower()
        for key in key_relationships:
            if key in rel and key_relationships[key] is None:
                key_relationships[key] = contact
                break

    lines: list[str] = []
    for _rel_type, matched in key_relationships.items():
        if matched is not None:
            lines.append(f"- **{matched.name}** — {matched.relationship}")
    # Add a note about total contacts
    lines.append(
        f"- Plus {len(contacts) - len(lines)} other contacts (coworkers, friends, services)"
    )

    contacts_section = "\n".join(lines)

    # Find spouse name from contacts
    spouse_name = "Sarah"
    for contact in contacts:
        if "wife" in contact.relationship.lower():
            # Extract first name
            spouse_name = contact.name.split()[0]
            break

    return PERSONA_TEMPLATE.format(
        name=person.name,
        occupation=person.occupation,
        home_address=person.home_address,
        office_address=person.office_address,
        spouse_name=spouse_name,
        agent_name=agent_identity.name,
        contacts_section=contacts_section,
    )
