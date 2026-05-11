import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum  # noqa: F401
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of Python 3.11 StrEnum for Python 3.9+."""
        def __str__(self) -> str:
            return self.value

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
