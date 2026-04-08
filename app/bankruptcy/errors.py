from __future__ import annotations


class BankruptcyError(RuntimeError):
    pass


class BankruptcyValidationError(BankruptcyError):
    pass


class BankruptcyConfigurationError(BankruptcyError):
    pass


class BankruptcyAuthorizationError(BankruptcyError):
    pass


class BankruptcyNotFoundError(BankruptcyError):
    pass
