"""Pydantic schemas shared across API + Agent + RAG layers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OnboardingRequest(BaseModel):
    """Inbound request from the React UI."""

    skills: list[str] = Field(..., description="Normalised skill tags, e.g. ['python', 'fastapi'].")
    direction: str = Field(..., description="Free-text interest, e.g. 'LLM application framework'.")
    hours_per_week: int = Field(5, ge=1, le=80)
    top_k_repos: int = Field(3, ge=1, le=10)


class RepoMeta(BaseModel):
    """Normalised repository metadata collected from GitHub."""

    id: int
    full_name: str
    name: str
    owner: str
    description: str | None = None
    html_url: str
    stars: int
    forks: int
    open_issues: int
    primary_language: str | None = None
    topics: list[str] = Field(default_factory=list)
    license_spdx: str | None = None
    default_branch: str
    pushed_at: datetime | None = None
    updated_at: datetime | None = None


class GitHubIssue(BaseModel):
    """Normalised GitHub Issue payload used by ETL and KG ingestion."""

    id: int
    repo: str
    number: int
    title: str
    body: str | None = None
    state: Literal["open", "closed"]
    labels: list[str] = Field(default_factory=list)
    author_login: str | None = None
    author_association: str | None = None
    comments: int = 0
    html_url: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class GitHubPullRequest(BaseModel):
    """Normalised GitHub Pull Request payload used by ETL and KG ingestion."""

    id: int
    repo: str
    number: int
    title: str
    body: str | None = None
    state: Literal["open", "closed"]
    merged_at: datetime | None = None
    author_login: str | None = None
    author_association: str | None = None
    comments: int = 0
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    html_url: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class RepoCandidate(BaseModel):
    full_name: str
    stars: int
    primary_language: str | None = None
    score: float = Field(..., description="Match score from GCN heterogeneous embedding.")
    reason: str = Field("", description="Short LLM-generated rationale.")


class IssueCandidate(BaseModel):
    repo: str
    number: int
    title: str
    labels: list[str] = Field(default_factory=list)
    friendliness: float = Field(..., description="GCN predicted newcomer-friendliness in [0, 1].")
    skill_match: float = Field(..., description="Skill vs. issue requirement similarity in [0, 1].")
    predicted_files: list[str] = Field(default_factory=list)
    similar_pr_ids: list[int] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    estimated_hours: float = 4.0


class Citation(BaseModel):
    type: Literal["code", "pr", "issue", "doc"]
    repo: str | None = None
    ref: str = Field(..., description="File path / PR number / Issue number / doc anchor.")
    lines: list[int] | None = None
    url: str | None = None


class AgentTrace(BaseModel):
    """A single node execution record from the LangGraph agent."""

    node: str
    input: dict
    output: dict
    elapsed_ms: int


class OnboardingPlan(BaseModel):
    """Final structured output returned to the frontend."""

    repo: RepoCandidate
    issues: list[IssueCandidate]
    summary: str
    citations: list[Citation]
    trace: list[AgentTrace] = Field(default_factory=list)
