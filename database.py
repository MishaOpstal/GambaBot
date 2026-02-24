import redis
import json
from typing import Optional, Dict, List, Any
from config import Config


class Database:
    """Redis database wrapper for bot data management"""

    def __init__(self):
        self.redis = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD
        )

    # ==================== User Points ====================

    def get_user_points(self, guild_id: int, user_id: int, streamer_id: int) -> int:
        """Get user's points for a specific streamer in a guild"""
        key = f"points:{guild_id}:{user_id}:{streamer_id}"
        points = self.redis.get(key)
        return int(points) if points else Config.DEFAULT_STARTING_POINTS

    def set_user_points(self, guild_id: int, user_id: int, streamer_id: int, points: int):
        """Set user's points for a specific streamer in a guild"""
        key = f"points:{guild_id}:{user_id}:{streamer_id}"
        self.redis.set(key, points)

    def add_user_points(self, guild_id: int, user_id: int, streamer_id: int, amount: int) -> int:
        """Add points to user's balance and return new total"""
        key = f"points:{guild_id}:{user_id}:{streamer_id}"
        new_total = self.redis.incr(key, amount)
        return new_total

    def get_all_user_points(self, guild_id: int, user_id: int) -> Dict[int, int]:
        """Get all points for a user across all streamers in a guild"""
        pattern = f"points:{guild_id}:{user_id}:*"
        points_dict = {}

        for key in self.redis.scan_iter(match=pattern):
            streamer_id = int(key.split(":")[-1])
            points = int(self.redis.get(key))
            points_dict[streamer_id] = points

        return points_dict

    # ==================== Streamer Settings ====================

    def get_streamer_point_name(self, guild_id: int, streamer_id: int) -> str:
        """Get the custom point name for a streamer"""
        key = f"streamer:{guild_id}:{streamer_id}:point_name"
        name = self.redis.get(key)
        return name if name else "points"

    def set_streamer_point_name(self, guild_id: int, streamer_id: int, name: str):
        """Set the custom point name for a streamer"""
        key = f"streamer:{guild_id}:{streamer_id}:point_name"
        self.redis.set(key, name)

    def get_streamer_earn_rate(self, guild_id: int, streamer_id: int) -> int:
        """Get the points earning rate for a streamer"""
        key = f"streamer:{guild_id}:{streamer_id}:earn_rate"
        rate = self.redis.get(key)
        return int(rate) if rate else Config.DEFAULT_POINTS_EARN_RATE

    def set_streamer_earn_rate(self, guild_id: int, streamer_id: int, rate: int):
        """Set the points earning rate for a streamer"""
        key = f"streamer:{guild_id}:{streamer_id}:earn_rate"
        self.redis.set(key, rate)

    # ==================== Predictions ====================

    def create_prediction(self, guild_id: int, prediction_data: Dict[str, Any]):
        """Create a new prediction"""
        key = f"prediction:{guild_id}"
        self.redis.set(key, json.dumps(prediction_data))

    def get_prediction(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get active prediction for a guild"""
        key = f"prediction:{guild_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def delete_prediction(self, guild_id: int):
        """Delete a prediction"""
        key = f"prediction:{guild_id}"
        self.redis.delete(key)

    def get_all_active_predictions(self) -> List[int]:
        """Get all guild IDs with active predictions"""
        guild_ids = []
        for key in self.redis.scan_iter(match="prediction:*"):
            guild_id = int(key.split(":")[1])
            guild_ids.append(guild_id)
        return guild_ids

    # ==================== Prediction Bets ====================

    def place_bet(self, guild_id: int, user_id: int, side: str, amount: int):
        """Place a bet on a prediction"""
        key = f"bet:{guild_id}:{user_id}"
        bet_data = {"side": side, "amount": amount}
        self.redis.set(key, json.dumps(bet_data))

    def get_bet(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's bet for a prediction"""
        key = f"bet:{guild_id}:{user_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def get_all_bets(self, guild_id: int) -> Dict[int, Dict[str, Any]]:
        """Get all bets for a guild's prediction"""
        pattern = f"bet:{guild_id}:*"
        bets = {}

        for key in self.redis.scan_iter(match=pattern):
            user_id = int(key.split(":")[-1])
            bet_data = json.loads(self.redis.get(key))
            bets[user_id] = bet_data

        return bets

    def clear_all_bets(self, guild_id: int):
        """Clear all bets for a guild"""
        pattern = f"bet:{guild_id}:*"
        for key in self.redis.scan_iter(match=pattern):
            self.redis.delete(key)

    # ==================== Stream Tracking ====================

    def add_stream_viewer(self, guild_id: int, streamer_id: int, viewer_id: int):
        """Add a viewer to a streamer's viewer set"""
        key = f"stream:{guild_id}:{streamer_id}:viewers"
        self.redis.sadd(key, viewer_id)

    def remove_stream_viewer(self, guild_id: int, streamer_id: int, viewer_id: int):
        """Remove a viewer from a streamer's viewer set"""
        key = f"stream:{guild_id}:{streamer_id}:viewers"
        self.redis.srem(key, viewer_id)

    def get_stream_viewers(self, guild_id: int, streamer_id: int) -> set:
        """Get all viewers for a streamer"""
        key = f"stream:{guild_id}:{streamer_id}:viewers"
        viewers = self.redis.smembers(key)
        return {int(v) for v in viewers}

    def clear_stream_viewers(self, guild_id: int, streamer_id: int):
        """Clear all viewers for a streamer"""
        key = f"stream:{guild_id}:{streamer_id}:viewers"
        self.redis.delete(key)

    def get_all_active_streams(self, guild_id: int) -> List[int]:
        """Get all active streamer IDs in a guild"""
        pattern = f"stream:{guild_id}:*:viewers"
        streamer_ids = []

        for key in self.redis.scan_iter(match=pattern):
            parts = key.split(":")
            if len(parts) >= 3:
                streamer_id = int(parts[2])
                if self.redis.scard(key) > 0:  # Only if there are viewers
                    streamer_ids.append(streamer_id)

        return streamer_ids

    # ==================== Utility ====================

    def ping(self) -> bool:
        """Check if Redis connection is alive"""
        try:
            return self.redis.ping()
        except:
            return False


# Global database instance
db = Database()