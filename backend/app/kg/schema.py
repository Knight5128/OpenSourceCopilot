"""Knowledge-graph ontology.

Edit this file when you add/rename node labels or relationship types.
The constants here are imported by the ETL pipeline and Cypher templates,
so the ontology stays in lockstep with the code.
"""

from __future__ import annotations

# ----------------------------- Node labels -----------------------------
REPO = "Repo"
MODULE = "Module"
FUNCTION = "Function"
ISSUE = "Issue"
PR = "PR"
CONTRIBUTOR = "Contributor"
SKILL = "Skill"

NODE_LABELS: tuple[str, ...] = (
    REPO,
    MODULE,
    FUNCTION,
    ISSUE,
    PR,
    CONTRIBUTOR,
    SKILL,
)

# ----------------------------- Relationship types ----------------------
CONTAINS = "CONTAINS"         # Module -> Function
HAS_MODULE = "HAS_MODULE"     # Repo   -> Module
CALLS = "CALLS"               # Function -> Function
AFFECTS = "AFFECTS"           # Issue  -> Module
MODIFIES = "MODIFIES"         # PR     -> Function
CLOSES = "CLOSES"             # PR     -> Issue
AUTHORED = "AUTHORED"         # Contributor -> PR
HAS_SKILL = "HAS_SKILL"       # Contributor -> Skill
REQUIRES = "REQUIRES"         # Issue  -> Skill

REL_TYPES: tuple[str, ...] = (
    HAS_MODULE,
    CONTAINS,
    CALLS,
    AFFECTS,
    MODIFIES,
    CLOSES,
    AUTHORED,
    HAS_SKILL,
    REQUIRES,
)

# ----------------------------- Constraint DDL --------------------------
CONSTRAINTS_CYPHER: list[str] = [
    f"CREATE CONSTRAINT repo_full_name IF NOT EXISTS FOR (r:{REPO}) REQUIRE r.full_name IS UNIQUE",
    (
        f"CREATE CONSTRAINT issue_key IF NOT EXISTS "
        f"FOR (i:{ISSUE}) REQUIRE (i.repo, i.number) IS UNIQUE"
    ),
    f"CREATE CONSTRAINT pr_key IF NOT EXISTS FOR (p:{PR}) REQUIRE (p.repo, p.number) IS UNIQUE",
    (
        f"CREATE CONSTRAINT contributor_login IF NOT EXISTS "
        f"FOR (c:{CONTRIBUTOR}) REQUIRE c.login IS UNIQUE"
    ),
    f"CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:{SKILL}) REQUIRE s.name IS UNIQUE",
]
