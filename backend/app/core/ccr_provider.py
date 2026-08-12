"""CCRDataProvider abstraction. Separates "where the CCR decision data
comes from" from "how it's classified/prioritised/decided"
(core/ccr_priority.py never reads STORE.ccr_counterparties directly - it
goes through a provider instance).

InternalSampleCCRProvider is the only implementation in this POC: it reads
the local, fictional, synthetic dataset (backend/data/ccr_counterparties.json).

A future ProductionCCRProvider would implement the same interface against
real internal systems - this file does NOT invent real Citi endpoints,
schemas, or connection details; it only defines the shape a production
implementation would need to satisfy so the rest of the platform (driver
classifier, priority engine, Decision object, every UI page) would keep
working unchanged.
"""
from abc import ABC, abstractmethod


class CCRDataProvider(ABC):
    @abstractmethod
    def get_counterparty_master(self):
        """List of counterparty/legal-entity records (identity, type, rating, watchlist)."""

    @abstractmethod
    def get_exposure_metrics(self):
        """RC / PFE / NSE / settlement exposure snapshots (current + previous)."""

    @abstractmethod
    def get_exposure_movers(self):
        """Delta PFE / RC / MTM movers, independent of the priority engine."""

    @abstractmethod
    def get_stress_movers(self):
        """Delta NSE / stress-exposure movers."""

    @abstractmethod
    def get_sensitivities(self):
        """FX delta / DV01 / CS01 / equity delta / vega where available."""

    @abstractmethod
    def get_trades(self):
        """Trade-level detail: product, notional, direction, unmatched status."""

    @abstractmethod
    def get_netting_sets(self):
        """Netting-set membership per counterparty."""

    @abstractmethod
    def get_collateral(self):
        """Collateral type / CSA / haircut per counterparty."""

    @abstractmethod
    def get_limits(self):
        """Limit records, each with an explicit limit_type - never a bare number."""

    @abstractmethod
    def get_breaches(self):
        """Active breach records: age, SLA, root cause, excess."""

    @abstractmethod
    def get_model_impacts(self):
        """Portfolio-level model/simulation run summaries (facility counts, total impact, categories)."""

    @abstractmethod
    def get_full_records(self):
        """Full merged per-counterparty records (all of the above joined by id) -
        what core/ccr_priority.py actually classifies/prioritises. Split out
        from the granular methods above because a production provider would
        likely source exposure/limits/collateral from different systems and
        need to join them; this method is where that join happens."""


class InternalSampleCCRProvider(CCRDataProvider):
    """Current (only) implementation: reads the local synthetic fictional
    dataset. Tagged SYNTHETIC_CCR_DECISION_DATA end to end - this is NOT a
    real internal-systems integration."""

    def __init__(self, store):
        self._store = store

    def get_counterparty_master(self):
        return [{k: r[k] for k in ("id", "name", "legal_entity", "counterparty_type", "rating", "watchlist",
                                     "coverage_owner", "is_synthetic", "source_type")}
                for r in self._store.ccr_counterparties]

    def get_exposure_metrics(self):
        return [{"id": r["id"], **r["exposure"]} for r in self._store.ccr_counterparties]

    def get_exposure_movers(self):
        return [{"id": r["id"], "pfe_previous": r["exposure"]["pfe_previous"], "pfe_current": r["exposure"]["pfe_current"],
                  "rc_previous": r["exposure"]["rc_previous"], "rc_current": r["exposure"]["rc_current"]}
                for r in self._store.ccr_counterparties]

    def get_stress_movers(self):
        return [{"id": r["id"], "nse_previous": r["exposure"]["nse_previous"], "nse_current": r["exposure"]["nse_current"]}
                for r in self._store.ccr_counterparties]

    def get_sensitivities(self):
        return [{"id": r["id"], **r["sensitivities"]} for r in self._store.ccr_counterparties]

    def get_trades(self):
        return [{"id": r["id"], "product": r["product"], "notional": r.get("notional"),
                  "direction": r.get("direction"), "unmatched_trades": r.get("unmatched_trades")}
                for r in self._store.ccr_counterparties]

    def get_netting_sets(self):
        return [{"id": r["id"], "netting_set": r.get("netting_set")} for r in self._store.ccr_counterparties]

    def get_collateral(self):
        return [{"id": r["id"], "collateral": r.get("collateral")} for r in self._store.ccr_counterparties]

    def get_limits(self):
        return [{"id": r["id"], **r["limit"]} for r in self._store.ccr_counterparties]

    def get_breaches(self):
        return [{"id": r["id"], **r["breach"]} for r in self._store.ccr_counterparties if r.get("breach")]

    def get_model_impacts(self):
        return list(self._store.ccr_model_impacts)

    def get_full_records(self):
        # In this POC, the "join" is trivial - all categories already live
        # on one record per counterparty in the local dataset. A production
        # provider would perform a real join here across systems.
        return list(self._store.ccr_counterparties)


def get_ccr_provider():
    from .data import STORE
    return InternalSampleCCRProvider(STORE)
