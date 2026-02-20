import redis

from libs.common.config import get_settings
from libs.common.enums import ErrorCode


class RateLimitedError(PermissionError):
    code = ErrorCode.rate_limited


class RateLimiter:
    def __init__(self) -> None:
        s = get_settings()
        self.limit = s.rate_limit_per_hour
        self.client = redis.Redis.from_url(s.redis_url, decode_responses=True)

    def check_and_increment(self, user_id: str) -> None:
        key = f'rl:create_job:{user_id}'
        value = self.client.incr(key)
        if value == 1:
            self.client.expire(key, 3600)
        if value > self.limit:
            raise RateLimitedError('rate limit exceeded')
