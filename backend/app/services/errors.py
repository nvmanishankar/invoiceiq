"""Form validation problems, one plain-English message per field, so the UI can show each next to its input."""


class Invalid(Exception):
    def __init__(self, errors: dict[str, str], status: int = 422):
        self.errors = errors
        self.status = status
        first = next(iter(errors.values()), "Please check the form.")
        more = len(errors) - 1
        super().__init__(first if not more else f"{first} (and {more} more problem{'s' if more > 1 else ''})")

    @property
    def message(self) -> str:
        return str(self)
