from .base import Domain


def get_domains() -> dict:
    from .finance import FinanceDomain
    from .mail import MailDomain
    ds = [FinanceDomain(), MailDomain()]
    return {d.name: d for d in ds}


def get_domain(name: str) -> Domain:
    ds = get_domains()
    if name not in ds:
        raise KeyError(f"unknown domain {name!r}; choose from {sorted(ds)}")
    return ds[name]
