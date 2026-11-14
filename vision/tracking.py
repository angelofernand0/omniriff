"""Fail-closed wrist tracking for MediaPipe's unordered hand detections."""
import math


class HandSelector:
    """Follow the nearest wrist and reject sudden hand-identity changes.

    Coordinates are normalized image-space (0..1). After a prolonged mismatch
    or absence, forget the old wrist; the gesture Controller still requires an
    open hand before it can re-arm.
    """

    def __init__(self, max_jump=0.30, forget_after=15):
        if not math.isfinite(max_jump) or not 0 < max_jump <= 1:
            raise ValueError('max_jump must be finite and in (0, 1]')
        if not isinstance(forget_after, int) or forget_after < 1:
            raise ValueError('forget_after must be a positive integer')
        self.max_jump = max_jump
        self.forget_after = forget_after
        self.center = None
        self.misses = 0

    def _miss(self):
        self.misses += 1
        if self.misses >= self.forget_after:
            self.center = None
        return None

    def select(self, centers):
        """Return selected detection index, or None when tracking is unsafe."""
        valid = []
        for index, center in enumerate(centers):
            if center is None or len(center) != 2:
                continue
            x, y = center
            if not all(math.isfinite(value) and 0 <= value <= 1 for value in (x, y)):
                continue
            valid.append((index, (x, y)))
        if not valid:
            return self._miss()

        if self.center is None:
            index, self.center = valid[0]
            self.misses = 0
            return index

        index, center = min(valid, key=lambda item: math.dist(item[1], self.center))
        if math.dist(center, self.center) > self.max_jump:
            return self._miss()
        self.center = center
        self.misses = 0
        return index
