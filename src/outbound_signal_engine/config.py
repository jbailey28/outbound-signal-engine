"""Configuration: the columns we expect from the Salesforce Printable View.

Keeping the column contract in one place makes the parser easy to audit and
easy to adjust when a real export shows slightly different header text.
"""

from __future__ import annotations

# Canonical field names used throughout the system (snake_case).
FIELDS = [
    "account_name",
    "website",
    "competitors",
    "industry",
    "sub_industry",
]

# Map of canonical field -> list of header strings we might see in the PDF.
# Matching is case-insensitive and ignores surrounding whitespace/punctuation.
# Add new aliases here when a real export uses different wording.
HEADER_ALIASES: dict[str, list[str]] = {
    "account_name": ["account name", "account", "name", "company", "company name"],
    "website": ["website", "web site", "url", "domain", "site"],
    "competitors": ["competitors", "competitor", "current platform", "platform"],
    "industry": ["industry"],
    "sub_industry": ["sub-industry", "sub industry", "subindustry", "sub_industry"],
}

# A row needs at least an account name to be worth keeping.
REQUIRED_FIELDS = ["account_name"]
