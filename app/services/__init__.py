"""Service layer — orchestrates repositories + engines (Section 5.1).
Routers call exactly one service method each; services manage
transactions and call engines for all scoring/aggregation math.
"""
