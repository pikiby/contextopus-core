"""Request-scoped cleanup must preserve failures without claiming live groups stopped."""

import errno
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from contextopus.core.module_management import bridge, processes


def child(exited=True):
    return SimpleNamespace(pid=12345, poll=Mock(return_value=1 if exited else None),
                           kill=Mock(), wait=Mock(return_value=1))


@pytest.fixture
def posix_signal(monkeypatch):
    # Fake POSIX process tests must not depend on Windows exposing SIGKILL.
    monkeypatch.setattr(processes, 'signal', SimpleNamespace(SIGKILL=9))


def test_exited_leader_permission_failure_never_resignals_a_reusable_group_id(monkeypatch, posix_signal):
    process = child()
    denied = PermissionError(errno.EPERM, 'group cleanup unverified')
    killpg = Mock(side_effect=denied)
    monkeypatch.setattr(processes, 'os', SimpleNamespace(name='posix', killpg=killpg))
    with pytest.raises(PermissionError) as failure:
        processes.terminate(process)
    assert failure.value is denied
    killpg.assert_called_once_with(process.pid, processes.signal.SIGKILL)
    process.kill.assert_not_called()
    process.wait.assert_called_once_with(timeout=5)


def test_live_leader_permission_failure_reaps_direct_child_but_reports_group_unverified(monkeypatch, posix_signal):
    process = child(exited=False)
    denied = PermissionError(errno.EPERM, 'group remains inaccessible')
    killpg = Mock(side_effect=denied)
    monkeypatch.setattr(processes, 'os', SimpleNamespace(name='posix', killpg=killpg))
    with pytest.raises(PermissionError) as failure:
        processes.terminate(process)
    assert failure.value is denied
    killpg.assert_called_once_with(process.pid, processes.signal.SIGKILL)
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)


def test_missing_group_still_terminates_a_live_direct_child(monkeypatch, posix_signal):
    process = child(exited=False)
    monkeypatch.setattr(processes, 'os', SimpleNamespace(name='posix',
        killpg=Mock(side_effect=ProcessLookupError(errno.ESRCH, 'gone'))))
    processes.terminate(process)
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)


def test_original_failure_stays_primary_with_cleanup_failure_as_cause(monkeypatch):
    primary = RuntimeError('original handler failure')
    cleanup = PermissionError(errno.EPERM, 'group cleanup denied')
    monkeypatch.setattr(bridge, 'terminate', Mock(side_effect=cleanup))
    with pytest.raises(RuntimeError) as failure:
        try:
            raise primary
        finally:
            bridge._terminate_preserving_error(child(), primary=primary)
    assert failure.value is primary
    assert failure.value.__cause__ is cleanup
    assert any('cleanup failed' in note for note in failure.value.__notes__)


def test_cleanup_failure_after_success_remains_a_failure(monkeypatch):
    cleanup = PermissionError(errno.EPERM, 'group cleanup denied')
    monkeypatch.setattr(bridge, 'terminate', Mock(side_effect=cleanup))
    with pytest.raises(PermissionError) as failure:
        bridge._terminate_preserving_error(child())
    assert failure.value is cleanup


def test_job_assignment_failure_retains_original_error_and_closes_stdio(tmp_path, monkeypatch):
    process = child()
    process.stdin, process.stdout = BytesIO(), BytesIO()
    primary = RuntimeError('job assignment failed')
    cleanup = PermissionError(errno.EPERM, 'cleanup denied')
    monkeypatch.setattr(bridge.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(bridge, 'windows_job', Mock(side_effect=primary))
    monkeypatch.setattr(bridge, 'terminate', Mock(side_effect=cleanup))
    with pytest.raises(RuntimeError) as failure:
        bridge.invoke(['unused'], arguments={}, module='sample', kind='query', storage=None,
                      declared_storage=False, cwd=tmp_path, env={}, timeout=5)
    assert failure.value is primary and failure.value.__cause__ is cleanup
    assert process.stdin.closed and process.stdout.closed
