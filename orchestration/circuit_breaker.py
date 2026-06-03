class CircuitBreaker:

    def __init__(self) -> None:
        self.open = False

    def allow(self) -> bool:
        return not self.open
