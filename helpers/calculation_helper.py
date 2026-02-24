import math
from typing import Dict, Tuple


def calculate_percentages(believe_pool: Dict[int, int], doubt_pool: Dict[int, int]) -> Tuple[int, int]:
    """Calculate percentage distribution between believe and doubt pools"""
    total_believe = sum(believe_pool.values()) if believe_pool else 0
    total_doubt = sum(doubt_pool.values()) if doubt_pool else 0
    total = total_believe + total_doubt

    if total == 0:
        return 0, 0

    believe_percent = math.floor((total_believe / total) * 100)
    doubt_percent = math.floor((total_doubt / total) * 100)

    return believe_percent, doubt_percent


def calculate_winnings(loser_bets: Dict[int, int], winner_bets: Dict[int, int]) -> Dict[int, int]:
    """
    Calculate winnings for each winner based on their share of the winner pool
    Winners get their bet back + proportional share of loser pool
    """
    if not winner_bets:
        return {}

    loser_pool_total = sum(loser_bets.values())
    winner_pool_total = sum(winner_bets.values())
    winnings = {}

    for user_id, bet_amount in winner_bets.items():
        # Calculate their share of the winner pool
        share = bet_amount / winner_pool_total
        # Their winnings = their bet + their share of loser pool
        winnings[user_id] = bet_amount + math.floor(share * loser_pool_total)

    return winnings
