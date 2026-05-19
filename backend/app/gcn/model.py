"""GNN model definitions for the two learning tasks.

Task 1 · Issue newcomer-friendliness  (binary node classification)
Task 2 · Contributor x Repo matching  (heterogeneous link prediction)

The actual training loop lives in `train.py`. Member A owns this file.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv, GCNConv


class IssueFriendlinessGNN(nn.Module):
    """Two-layer GCN that scores Issue nodes."""

    def __init__(self, in_dim: int, hidden_dim: int = 64) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, hidden_dim)
        self.head = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.conv1(x, edge_index))
        h = F.dropout(h, p=0.3, training=self.training)
        h = F.relu(self.conv2(h, edge_index))
        return torch.sigmoid(self.head(h)).squeeze(-1)


class HeteroMatchGAT(nn.Module):
    """Single-homogeneous-projection GAT baseline for contributor-repo matching.

    For a fully heterogeneous version, swap in `torch_geometric.nn.HeteroConv`
    with `RGCNConv` once the homogeneous baseline is reproduced.
    """

    def __init__(self, in_dim: int, hidden_dim: int = 128, heads: int = 4) -> None:
        super().__init__()
        self.conv1 = GATConv(in_dim, hidden_dim, heads=heads, dropout=0.2)
        self.conv2 = GATConv(hidden_dim * heads, hidden_dim, heads=1, dropout=0.2)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = F.elu(self.conv1(x, edge_index))
        return self.conv2(h, edge_index)
