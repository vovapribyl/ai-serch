"""Trusted local composition: the sole supervisor owns all build admissions."""

from threading import Lock

from product_search.infrastructure.replenishment_repository import digest
from product_search.infrastructure.replenishment_supervisor import Supervisor
from product_search.search.corpus_replenishment import (
    ReplenishmentController,
    ResourceWait,
    product_readiness,
)
from product_search.search.replenishment_contracts import (
    BuildResult,
    ExecutionPackage,
    ReplenishmentError,
    SelectedPhoto,
    SelectedProduct,
)


class LocalReplenishmentApplication:
    def __init__(
        self,
        root,
        repository_factory,
        profile,
        artifacts,
        worker_factory,
        clock,
        *,
        authorize_build,
        authorize_search,
        observe,
        quiesce,
        summary_reader,
        claim_build=None,
    ):
        self.claim_build = claim_build or (lambda owner, package: None)
        self.repository_factory, self.profile = repository_factory, profile
        self.artifacts, self.worker_factory, self.clock = artifacts, worker_factory, clock
        self.authorize_build, self.authorize_search = authorize_build, authorize_search
        self.summary_reader = summary_reader
        self.repository = None
        self._operation = Lock()
        self.poll_resources = None
        self._wait_policy = None
        self.supervisor = Supervisor(
            root,
            issue_owner=self._issue_owner,
            observe=observe,
            quiesce=quiesce,
            clock=clock.monotonic,
        )

    def _admit_resources(self, operation_seconds):
        while True:
            try:
                observation = self.supervisor.observe()
            except Exception:  # noqa: BLE001 -- unknown resource observations are a hard STOP.
                observation = None
            if self._wait_policy.admit(observation, operation_seconds):
                return True
            if self._wait_policy.reason:
                raise ReplenishmentError(self._wait_policy.reason)
            if self.poll_resources is None:
                raise ReplenishmentError("RESOURCE_STOP")
            before = self.clock.monotonic()
            cutoff = min(
                self._wait_policy.wait_started + 300,
                self._wait_policy.end_at - self._wait_policy.package.cleanup_reserve_seconds,
            )
            self.poll_resources(cutoff)
            if self.clock.monotonic() <= before:
                raise ReplenishmentError("RESOURCE_STOP")

    def _issue_owner(self, mode, package):
        epoch = (
            self.supervisor.owner.epoch
            if self.supervisor.owner
            else self.repository.read_owner_epoch()
        )
        return self.repository.issue_owner(mode, epoch)

    def _search_owner(self, package):
        if self.authorize_search(package) is not True:
            raise ReplenishmentError("INVALID_SCOPE")
        self.supervisor._require_resources(package)
        return self._issue_owner("SEARCH", package)

    def initialize_search(self, package):
        end = self.clock.monotonic() + package.overall_seconds
        self.repository = self.repository_factory(package, end)
        self.supervisor.activate_search(
            lambda: self._search_owner(package),
            end_at=end,
            stop_grace=package.stop_grace_seconds,
            kill_wait=package.kill_wait_seconds,
        )

    def status(self, run):
        return self.summary_reader(run, self.supervisor.mode)

    def start(self, package, inventory):
        if not self._operation.acquire(blocking=False):
            raise ReplenishmentError("BUSY")
        try:
            return self._start(package, inventory)
        finally:
            self._operation.release()

    def _start(self, package, inventory=None, *, saved_run=None, retry=None):
        try:
            package = ExecutionPackage(**package)
            if (
                package.scope != (retry[0] if retry else "RESUME" if saved_run else "START")
                or self.authorize_build(package) is not True
            ):
                raise ReplenishmentError("INVALID_SCOPE")
            products = tuple(
                SelectedProduct(
                    p["corpus_version_id"],
                    p["product_record_id"],
                    p["expected_head_version"],
                    tuple(SelectedPhoto(**f) for f in p["photos"]),
                )
                for p in (inventory or [])
            )
        except (KeyError, TypeError):
            raise ReplenishmentError("INVALID_INPUT") from None
        started = self.clock.monotonic()
        end = started + package.overall_seconds
        self.repository = self.repository_factory(package, end)
        resume_refs = None
        if saved_run:
            products, resume_refs = self.repository.read_resume_inventory(saved_run)
        elif retry:
            products, resume_refs = self.repository.read_retry_inventory(*retry[1:])
        self.repository.validate_inventory(products)
        if digest(self.profile) != package.semantic_profile_sha:
            raise ReplenishmentError("PROFILE_MISMATCH")
        self._wait_policy = ResourceWait(package, end, self.clock)
        self.supervisor.await_resources = lambda pkg, limit, operation: self._admit_resources(
            operation
        )
        owner = None
        try:
            owner = self.supervisor.begin_build(package, end_at=end)
            self.claim_build(owner, package)
            self.repository.register_profile(owner, self.profile)
            if retry and retry[0] == "RETRY_PHOTO":
                revisions = self.repository.bind_retry_photo(owner, *retry[1:], resume_refs)
            elif retry:
                revisions = self.repository.bind_retry_publication(owner, retry[1], resume_refs)
            elif saved_run:
                revisions = self.repository.bind_resume(owner, saved_run, resume_refs)
            else:
                revisions = self.repository.register_inventory(owner, products)
            self.queue = self.repository.read_queue(owner)
            if retry and retry[0] == "RETRY_PUBLICATION":
                result = BuildResult((), (), (), "COMPLETED")
            else:
                workers = self.worker_factory(self.repository, owner, package, end)
                result = ReplenishmentController(
                    self.repository, self.artifacts, workers, self.clock
                ).run(
                    self.queue, package, owner, started_at=started, admission=self._admit_resources
                )
            if result.reason == "COMPLETED":
                refs = {r.revision_ref: r for r in revisions}
                for revision in revisions:
                    if (
                        product_readiness(self.repository.revision_outcomes(revision.revision_ref))
                        == "NOT_PUBLISHABLE"
                    ):
                        try:
                            self._admit_resources(package.db_seconds)
                            self.repository.prepare_revision(revision, owner, self.artifacts)
                        except ReplenishmentError as error:
                            if str(error) != "NOT_PUBLISHABLE":
                                raise
                eligible = (
                    result.ready_revision_refs
                    if not saved_run and not retry
                    else tuple(
                        r.revision_ref
                        for r in revisions
                        if product_readiness(self.repository.revision_outcomes(r.revision_ref))
                        == "READY"
                    )
                )
                for ref in eligible:
                    self._admit_resources(package.db_seconds)
                    ready = self.repository.prepare_revision(refs[ref], owner, self.artifacts)
                    try:
                        active = self.repository.resolve_active("nail-search-v1").snapshot_ref
                    except ReplenishmentError as error:
                        if str(error) != "INDEX_NOT_READY":
                            raise
                        active = None
                    self._admit_resources(package.db_seconds)
                    receipt = self.repository.publish_revision(ready, active, owner)
                    if receipt.state == "UNKNOWN":
                        self.supervisor.require_recovery()
                        return self.status(owner.run_ref)
            self.repository.finish_run(owner, result.reason)
            if result.reason == "COMPLETED":
                self._admit_resources(package.db_seconds)
                self.supervisor.activate_search(
                    lambda: self._search_owner(package),
                    end_at=end,
                    stop_grace=package.stop_grace_seconds,
                    kill_wait=package.kill_wait_seconds,
                )
            else:
                self.supervisor.require_recovery()
            return self.status(owner.run_ref)
        except Exception as error:
            self.supervisor.require_recovery()
            if owner is not None and str(error) not in {"COMMIT_UNKNOWN", "CHECKPOINT_UNKNOWN"}:
                reason = (
                    str(error)
                    if str(error)
                    in {"DEADLINE", "RESOURCE_STOP", "ADMISSION_LIMIT", "WAIT_TIMEOUT"}
                    else "RECOVERY_REQUIRED"
                )
                try:
                    self.repository.finish_run(owner, reason)
                except ReplenishmentError:
                    pass  # An unconfirmed audit cannot overwrite the original failure or reopen search.
            raise

    def resume(self, package, run):
        if not self._operation.acquire(blocking=False):
            raise ReplenishmentError("BUSY")
        try:
            return self._start(package, saved_run=run)
        finally:
            self._operation.release()

    def _retry(self, package, retry):
        if not self._operation.acquire(blocking=False):
            raise ReplenishmentError("BUSY")
        try:
            return self._start(package, retry=retry)
        finally:
            self._operation.release()

    def retry_photo(self, package, revision, photo, expected_version):
        return self._retry(package, ("RETRY_PHOTO", revision, photo, expected_version))

    def retry_publication(self, package, revision):
        return self._retry(package, ("RETRY_PUBLICATION", revision))
