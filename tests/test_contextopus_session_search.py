import json
import socket
import threading
from contextopus.core.operations import OperationRegistry
from contextopus.modules.session_search import SessionSearch

def test_status_existing_socket_never_searches_or_launches(tmp_path):
    path=tmp_path/'index.sock'; observed=[]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path)); server.listen()
        def respond():
            client,_=server.accept()
            with client:
                request=json.loads(client.makefile('rb').readline()); observed.append(request)
                client.sendall(b'{"ok":true,"indexed":7}\n')
        thread=threading.Thread(target=respond); thread.start()
        result=SessionSearch(path).status(); thread.join(3)
    assert observed==[{'op':'status'}]
    assert result['daemon']['indexed']==7
    assert result['core_rag_migrated'] is False

def test_registration_validates_query_arguments():
    registry=OperationRegistry(); module=SessionSearch('/does/not/exist'); module.register(registry)
    status=registry.dispatch('query','session_search.status')
    assert status['state']=='unavailable'
    assert status['reason']
    assert 'session_search.open_tui' in registry.describe()['operations']['execute']

def test_separate_venv_discovers_installed_executable(tmp_path,monkeypatch):
    command=tmp_path/'session-search';command.write_text('#!/bin/sh\nexit 0\n');command.chmod(0o755)
    monkeypatch.setenv('PATH',str(tmp_path))
    monkeypatch.setattr('importlib.util.find_spec',lambda name:None)
    module=SessionSearch('/absent.sock')
    assert module.available()
    descriptor=module.launch_tui()
    assert descriptor['argv']==[str(command),'tui']
    assert descriptor['terminal_owner']=='client'

def test_declared_command_is_argv_without_shell_interpolation(tmp_path):
    import pytest
    command=tmp_path/'launcher with spaces';command.write_text('#!/bin/sh\nexit 0\n');command.chmod(0o755)
    payload='$(touch /tmp/should-not-exist); echo surprise'
    module=SessionSearch(command=[str(command),payload])
    assert module.launch_tui()['argv']==[str(command),payload]
    with pytest.raises(ValueError): SessionSearch(command='session-search tui; echo surprise')
