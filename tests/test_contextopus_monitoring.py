import sqlite3
from datetime import datetime,timedelta,timezone
from contextopus.core.monitoring import RootServices
from contextopus.core.operations import OperationRegistry
from contextopus.core.storage import StorageLayout

def test_status_absent_index_is_unknown_and_does_not_create_storage(tmp_path):
    root=tmp_path/'absent'; registry=OperationRegistry();registry.register_module('workspace',available=True,state='available',open_tui=False)
    service=RootServices(StorageLayout(root),None,registry)
    status=service.status()
    assert status['database']['stored_items'] is None
    assert status['resources']['cpu_percent'] is None
    assert status['modules'][0]['name']=='workspace'
    assert not root.exists()

def test_usage_24h_does_not_count_status_poll_or_old_requests(tmp_path):
    layout=StorageLayout(tmp_path);layout.analytics.mkdir(parents=True)
    with sqlite3.connect(layout.analytics/'operations.sqlite3') as db:
        db.execute('CREATE TABLE operations(started TEXT,operation TEXT,outcome TEXT,duration REAL)')
        now=datetime.now(timezone.utc)
        db.executemany('INSERT INTO operations VALUES(?,?,?,?)',[(now.isoformat(),'workspace.search','ok',0.2),(now.isoformat(),'core.status','ok',0.1),((now-timedelta(days=2)).isoformat(),'workspace.search','error',10)])
    result=RootServices(layout,None,OperationRegistry()).status()['usage']
    assert result['requests']==1 and result['errors']==0
    assert result['average_seconds']==0.2

def test_corrupt_index_reason_is_visible_and_not_zero(tmp_path):
    layout=StorageLayout(tmp_path);layout.rag.mkdir(parents=True)
    (layout.rag/'lancedb').mkdir()
    (layout.rag/'active.json').write_text('{invalid')
    status=RootServices(layout,None,OperationRegistry()).status()
    assert status['state']=='error'
    assert status['database']['error']
    assert status['database']['stored_items'] is None
