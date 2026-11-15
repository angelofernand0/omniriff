"""Bounded local readiness checks; never sends instrument controls."""
import asyncio
from dataclasses import dataclass
import http.client
import inspect
import json
import math
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit

MAX_FRAME_BYTES = 32768
ORIGIN = 'http://127.0.0.1:8080'


@dataclass
class Result:
    name: str
    green: bool
    detail: str


def validators():
    from jsonschema import Draft202012Validator
    root = Path(__file__).resolve().parents[2] / 'protocol'
    return {name: Draft202012Validator(json.loads((root / (name + '.schema.json')).read_text()))
            for name in ('state', 'hand', 'coach')}


def strict_json(payload):
    if not isinstance(payload, str):
        raise ValueError('expected a text JSON frame')
    def invalid(value):
        raise ValueError('non-finite JSON number')
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON number')
        return result
    return json.loads(payload, parse_constant=invalid, parse_float=finite_float)


def fresh(frame, max_age_ms):
    age = time.time() * 1000 - frame['timestamp_ms']
    if not -1000 <= age <= max_age_ms:
        raise ValueError(f'stale/future frame (age {age:.0f} ms)')
    return age


async def websocket_frame(port, validator, kind, timeout):
    from websockets.asyncio.client import connect
    options = dict(origin=ORIGIN, open_timeout=timeout, close_timeout=.1,
                   ping_interval=None, max_size=MAX_FRAME_BYTES, max_queue=1)
    # websockets 14 has no proxy option; 15+ may inherit an environment proxy.
    if 'proxy' in inspect.signature(connect).parameters:
        options['proxy'] = None
    async with connect(f'ws://127.0.0.1:{port}', **options) as socket:
        for _ in range(4):
            frame = strict_json(await socket.recv())
            validator.validate(frame)
            if kind == 'coach' and frame.get('type') != 'coach.frame':
                continue  # an audio/decision message is not a status snapshot
            return frame
    raise ValueError('no coach.frame status snapshot')


async def engine_check(port, validator, timeout):
    frame = await websocket_frame(port, validator, 'state', timeout)
    age = fresh(frame, 1000)
    adapters = ','.join(f'{key}={item["status"]}' for key, item in frame['adapters'].items())
    unhealthy = any(item['status'] in ('error', 'retrying', 'starting', 'stopped')
                    for item in frame['adapters'].values())
    unhealthy |= any(frame['adapters'][key]['status'] != 'running' for key in ('udp', 'websocket'))
    detail = (f'xruns={frame["xruns"]} (total); clips={frame["clipped_samples"]} (total); input_peak={frame["input_peak_dbfs"]:.1f} dBFS; '
              f'loop={frame["loop"]["state"]}; {adapters}; age={age:.0f}ms')
    if frame.get('replay') is not None:
        detail += '; REPLAY'
    return Result('engine', frame['xruns'] == 0 and not unhealthy, detail)


async def hand_check(port, validator, timeout):
    frame = await websocket_frame(port, validator, 'hand', timeout)
    age = fresh(frame, 500)
    return Result('hand', True, f'sending; {"hand present" if frame["present"] else "no hand seen"}; age={age:.0f}ms')


async def coach_check(port, validator, timeout):
    frame = await websocket_frame(port, validator, 'coach', timeout)
    replay = frame['session_id'].startswith('replay-')
    if replay and not frame['scripted']:
        return Result('coach', False, 'REPLAY metadata inconsistent: replay- session must be scripted; not a verified live feed')
    mode = ('REPLAY — recorded feed, not live' if replay else
            'SCRIPTED — NOT LIVE AI' if frame['scripted'] else
            'LIVE feed (model/credit not verified)')
    cue = frame.get('cue') or ''
    out_of_credit = 'out of credit' in cue.casefold()
    age = max(0, time.time() * 1000 - frame['timestamp_ms']) / 1000
    detail = f'{mode}; state={frame["state"]}; snapshot age={age:.1f}s (cached idle is normal)'
    if out_of_credit:
        detail += '; OUT OF CREDIT (reported cue)'
    return Result('coach', not out_of_credit, detail)


async def local(function, *args):
    """Bound blocking local probes without keeping the CLI alive on a stuck filesystem."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    def deliver(value, error):
        if not future.done():
            if error:
                future.set_exception(error)
            else:
                future.set_result(value)
    def work():
        try:
            value, error = function(*args), None
        except Exception as exc:
            value, error = None, exc
        try:
            loop.call_soon_threadsafe(deliver, value, error)
        except RuntimeError:
            pass  # deadline already closed the loop; daemon never prints late results
    threading.Thread(target=work, daemon=True).start()
    return await future


def dashboard_check(port, timeout):
    path = '/'
    for attempt in range(2):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
        response = None
        try:
            connection.request('GET', path, headers={'Origin': ORIGIN, 'Connection': 'close'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308) and attempt == 0:
                target = urlsplit(urljoin(f'http://127.0.0.1:{port}{path}', response.getheader('Location', '')))
                if target.scheme != 'http' or target.hostname != '127.0.0.1' or target.port != port or target.username or target.password:
                    raise ValueError('dashboard redirected outside the local endpoint')
                path = target.path or '/'
                if target.query:
                    path += '?' + target.query
                continue
            if response.status != 200:
                raise ValueError(f'HTTP {response.status}')
            content_type = response.getheader('Content-Type', '').lower()
            body = response.read(8192).lower()
            if 'text/html' not in content_type or b'omniriff' not in body or b'<' not in body:
                raise ValueError('HTTP response is not OmniRiff dashboard HTML')
            return Result('dashboard', True, f'HTTP 200 at 127.0.0.1:{port}')
        finally:
            if response is not None:
                response.close()
            connection.close()
    raise ValueError('dashboard redirect limit')


def take_directory_check(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('take directory missing; create it before the check')
    # No take is opened or changed. The unique empty probe is removed on exit.
    with tempfile.TemporaryFile(prefix='.omniriff-tablecheck-', dir=directory) as probe:
        probe.write(b'')
    return Result('takes', True, 'directory write probe passed; no takes changed')


def model_check(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('hand model must be a nonempty regular file')
    with path.open('rb') as stream:
        if not stream.read(1):
            raise ValueError('hand model is empty')
    return Result('model', True, 'hand model present/readable (not loaded)')


async def bounded(name, operation, timeout):
    try:
        return await asyncio.wait_for(operation, timeout)
    except asyncio.TimeoutError:
        return Result(name, False, f'timeout after {timeout:g}s')
    except Exception as exc:
        # One line; avoid printing frame payloads, server errors, or device identifiers.
        from jsonschema.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            detail = 'schema-invalid frame'
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            detail = str(exc).replace('\n', ' ')[:180]
        else:
            detail = type(exc).__name__ + '; endpoint/path unavailable'
        return Result(name, False, detail)


async def check(*, engine_port=47801, dashboard_port=8080, hand_port=47802, coach_port=47803,
                take_dir=Path('runs/takes'), model=Path('models/hand_landmarker.task'),
                no_vision=False, no_coach=False, timeout=1.5):
    if not .1 <= timeout <= 3:
        raise ValueError('timeout must be in [0.1,3] seconds')
    for port in (engine_port, dashboard_port, hand_port, coach_port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('ports must be integers in [1,65535]')
    schema = validators()
    jobs = [('engine', engine_check(engine_port, schema['state'], timeout)),
            ('dashboard', local(dashboard_check, dashboard_port, timeout)),
            ('takes', local(take_directory_check, take_dir))]
    if not no_vision:
        jobs += [('hand', hand_check(hand_port, schema['hand'], timeout)), ('model', local(model_check, model))]
    if not no_coach:
        jobs.append(('coach', coach_check(coach_port, schema['coach'], timeout)))
    return await asyncio.gather(*(bounded(name, operation, timeout) for name, operation in jobs))
