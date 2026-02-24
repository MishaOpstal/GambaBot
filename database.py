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
            password=Config.REDIS_PASSWORD,
            decode_responses=True  # Automatically decode bytes to strings
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

    def create_prediction(self, guild_id: int, prediction_id: str, prediction_data: Dict[str, Any]):
        """Create a new prediction with unique ID"""
        key = f"prediction:{guild_id}:{prediction_id}"
        self.redis.set(key, json.dumps(prediction_data))
        # Add to active predictions set
        self.redis.sadd(f"active_predictions:{guild_id}", prediction_id)

    def get_prediction(self, guild_id: int, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific prediction"""
        key = f"prediction:{guild_id}:{prediction_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def get_all_guild_predictions(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all active predictions for a guild"""
        prediction_ids = self.redis.smembers(f"active_predictions:{guild_id}")
        predictions = {}
        for pred_id in prediction_ids:
            prediction = self.get_prediction(guild_id, pred_id)
            if prediction:
                predictions[pred_id] = prediction
        return predictions

    def delete_prediction(self, guild_id: int, prediction_id: str):
        """Delete a prediction"""
        key = f"prediction:{guild_id}:{prediction_id}"
        self.redis.delete(key)
        # Remove from active predictions set
        self.redis.srem(f"active_predictions:{guild_id}", prediction_id)

    def get_all_active_predictions(self) -> Dict[int, List[str]]:
        """Get all guild IDs with their active prediction IDs"""
        guilds_predictions = {}
        for key in self.redis.scan_iter(match="active_predictions:*"):
            guild_id = int(key.split(":")[1])
            prediction_ids = list(self.redis.smembers(key))
            if prediction_ids:
                guilds_predictions[guild_id] = prediction_ids
        return guilds_predictions

    # ==================== Prediction Bets ====================

    def place_bet(self, guild_id: int, prediction_id: str, user_id: int, side: str, amount: int):
        """Place a bet on a specific prediction"""
        key = f"bet:{guild_id}:{prediction_id}:{user_id}"
        bet_data = {"side": side, "amount": amount}
        self.redis.set(key, json.dumps(bet_data))

    def get_bet(self, guild_id: int, prediction_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's bet for a specific prediction"""
        key = f"bet:{guild_id}:{prediction_id}:{user_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def get_all_bets(self, guild_id: int, prediction_id: str) -> Dict[int, Dict[str, Any]]:
        """Get all bets for a specific prediction"""
        pattern = f"bet:{guild_id}:{prediction_id}:*"
        bets = {}

        for key in self.redis.scan_iter(match=pattern):
            user_id = int(key.split(":")[-1])
            bet_data = json.loads(self.redis.get(key))
            bets[user_id] = bet_data

        return bets

    def clear_all_bets(self, guild_id: int, prediction_id: str):
        """Clear all bets for a specific prediction"""
        pattern = f"bet:{guild_id}:{prediction_id}:*"
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

    # ==================== Auth Tokens ====================

    def generate_auth_token(self, guild_id: int, user_id: int) -> str:
        """Generate a new auth token for a user in a specific guild"""
        import secrets
        token = secrets.token_urlsafe(32)
        key = f"auth_token:{guild_id}:{user_id}"
        self.redis.set(key, token)
        # Also store reverse lookup
        self.redis.set(f"token_lookup:{token}", f"{guild_id}:{user_id}")
        return token

    def get_auth_token(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get the auth token for a user in a specific guild"""
        key = f"auth_token:{guild_id}:{user_id}"
        return self.redis.get(key)

    def verify_auth_token(self, token: str) -> Optional[tuple]:
        """Verify an auth token and return (guild_id, user_id) if valid"""
        lookup = self.redis.get(f"token_lookup:{token}")
        if lookup:
            parts = lookup.split(":")
            return (int(parts[0]), int(parts[1]))
        return None


# Global database instance
db = Database()