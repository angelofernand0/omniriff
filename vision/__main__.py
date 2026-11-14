"""Webcam or paced recorded-video gesture sender."""
import argparse
import json
import math
from pathlib import Path
import socket
import time
from .control import Controller
from .tracking import HandSelector
from .scenes import SceneMorph, SCENES
from .hand_view import HandView
from .take import TakeRecorder
from .setlist import Setlist
from .metrics import FrameMetrics
from .hand_log import HandLog, hand_record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True, help='MediaPipe hand_landmarker.task model path')
    p.add_argument('--video', help='Recorded video; otherwise use webcam')
    p.add_argument('--camera', type=int, default=0)
    p.add_argument('--max-hand-jump', type=float, default=0.30,
                   help='maximum normalized wrist movement per frame before tracking fails closed')
    p.add_argument('--record-take', type=Path, help='save control events as replay JSONL; refuses overwrite')
    p.add_argument('--metrics-json', type=Path, help='save measured processing/rate summary on exit; refuses overwrite')
    p.add_argument('--hand-log', type=Path, help='append both wrist positions and Unix timestamps for coach take alignment')
    p.add_argument('--strum-hand', choices=('Left', 'Right'), default='Right', help='MediaPipe label of the strumming hand for hand-log analysis; verify camera orientation')
    p.add_argument('--no-hand-view', action='store_true', help='disable local dashboard landmark feed')
    p.add_argument('--hand-view-port', type=int, default=47802)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=47800)
    p.add_argument('--rate', type=float, default=20)
    p.add_argument('--control', choices=['filter', 'reverb'], default='filter')
    scene_options = p.add_mutually_exclusive_group()
    scene_options.add_argument('--scene', choices=sorted(SCENES), help='morph two effects with one gesture')
    scene_options.add_argument('--scene-file', type=Path, help='custom named from/to filter+reverb JSON')
    scene_options.add_argument('--setlist', type=Path, help='1..9 scenes; keys 1-9 select, n/p cycle')
    p.add_argument('--relative', action='store_true', help='pick up from current output value at pinch; move wrist to change it')
    p.add_argument('--calibration', type=Path, default=Path('vision-calibration.json'))
    p.add_argument('--calibrate', action='store_true')
    p.add_argument('--no-overlay', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='Validate and print events without UDP')
    args = p.parse_args(argv)
    if args.metrics_json and args.metrics_json.exists():
        p.error('metrics file exists; choose a new file')
    if args.calibrate and args.no_overlay:
        p.error('calibration requires overlay')
    if not math.isfinite(args.max_hand_jump) or not 0 < args.max_hand_jump <= 1:
        p.error('--max-hand-jump must be finite and in (0, 1]')
    if args.setlist and (args.no_overlay or args.calibrate):
        p.error('setlist switching requires the camera overlay and cannot be used during calibration')
    try:
        setlist = Setlist(json.loads(args.setlist.read_text())) if args.setlist else None
        scene = None
        if setlist:
            scene = setlist.current
        elif args.scene or args.scene_file:
            scene = SceneMorph(json.loads(args.scene_file.read_text()) if args.scene_file else SCENES[args.scene])
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    if scene and args.relative:
        p.error('scene mode uses calibrated absolute position; omit --relative')
    if scene and args.control != 'filter':
        p.error('scene mode controls both effects; omit --control reverb')
    import cv2
    import mediapipe as mp
    from jsonschema import Draft202012Validator
    config = json.loads(args.calibration.read_text()) if args.calibration.exists() else {}
    controller = Controller(rate=args.rate / 2 if scene else args.rate, control=args.control, relative=args.relative, **config)
    schema = json.loads((Path(__file__).resolve().parents[1] / 'protocol/control.schema.json').read_text())
    validator = Draft202012Validator(schema)
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6)
    cap = cv2.VideoCapture(args.video if args.video else args.camera)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError('Cannot open camera/video')
    fps = cap.get(cv2.CAP_PROP_FPS)
    if args.video and (not math.isfinite(fps) or fps <= 0):
        cap.release()
        raise ValueError('Recorded video must report a positive frame rate')
    start = time.monotonic()
    selector = HandSelector(max_jump=args.max_hand_jump)
    frame_number = count = 0
    last_stamp = -1
    pending = {}
    last_sent = minimum_interval = None
    take = None
    take_error_reported = False
    hand_view = None if args.no_hand_view else HandView(args.hand_view_port).start()
    hand_view_error_reported = False
    metrics = FrameMetrics()
    hand_log = None
    hand_log_error_reported = False
    try:
        if args.hand_log:
            hand_log = HandLog(args.hand_log)
        if args.record_take:
            take = TakeRecorder(args.record_take)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    if not args.video:
                        raise RuntimeError('Camera disconnected or frame capture failed')
                    break
                if args.video:
                    time.sleep(max(0, start + frame_number / fps - time.monotonic()))
                now = time.monotonic()
                captured_unix_ms = int(time.time() * 1000)
                stamp = max(last_stamp + 1, int((now - start) * 1000))
                last_stamp = stamp
                frame_number += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                if hand_log:
                    hand_log.record(hand_record(result, captured_unix_ms, args.strum_hand))
                    if hand_log.error and not hand_log_error_reported:
                        import sys
                        print('Hand log: ' + hand_log.error, file=sys.stderr)
                        hand_log_error_reported = True
                y = pinch = None
                confidence = 0.
                centers = [(hand[0].x, hand[0].y) for hand in result.hand_landmarks]
                selected = selector.select(centers)
                if selected is not None:
                    points = result.hand_landmarks[selected]
                    height, width = frame.shape[:2]
                    distance = lambda a, b: math.hypot((points[a].x - points[b].x) * width, (points[a].y - points[b].y) * height)
                    scale = distance(5, 17)
                    if scale > 1:
                        y = points[0].y
                        pinch = distance(4, 8) / scale
                        # Tasks exposes handedness score, not per-landmark confidence.
                        confidence = result.handedness[selected][0].score
                    if not args.no_overlay:
                        for point in points:
                            cv2.circle(frame, (int(point.x * width), int(point.y * height)), 3, (0, 255, 0), -1)
                event = controller.update(y, pinch, confidence, now, int(time.time() * 1000))
                if hand_view:
                    if hand_view.error and not hand_view_error_reported:
                        import sys
                        print('Hand view unavailable: ' + hand_view.error, file=sys.stderr)
                        hand_view_error_reported = True
                    landmarks = [[min(1., max(0., p.x)), min(1., max(0., p.y))] for p in points] if y is not None else []
                    hand_view.publish(dict(version=1, type='hand', timestamp_ms=int(time.time() * 1000),
                        present=y is not None, engaged=controller.active, confidence=confidence,
                        control=None if scene else args.control, value=controller.value, landmarks=landmarks))
                events = scene.events(event) if scene and event else ([event] if event else [])
                frame_events = 0
                for event in events if not args.calibrate else []:
                    validator.validate(event)
                    payload = json.dumps(event, separators=(',', ':'))
                    if args.dry_run:
                        print(payload, flush=True)
                    else:
                        sock.sendto(payload.encode(), (args.host, args.port))
                    if take:
                        take.record(event)
                        if take.error and not take_error_reported:
                            import sys
                            print('Take recording: ' + take.error, file=sys.stderr)
                            take_error_reported = True
                    count += 1
                    frame_events += 1
                    emitted = time.monotonic()
                    if last_sent is not None:
                        interval = emitted - last_sent
                        minimum_interval = interval if minimum_interval is None else min(minimum_interval, interval)
                    last_sent = emitted
                metrics.record(now, time.monotonic(), frame_events, hand_present=y is not None)
                if not args.no_overlay:
                    label = 'CALIBRATE: l low, h high, s save' if args.calibrate else f'{scene.name if scene else args.control}: {controller.value} active={controller.active} events={count}'
                    cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 255), 1)
                    if setlist:
                        cue = f'SCENE {setlist.index + 1}/{len(setlist.scenes)} | 1-9 select, n/p cycle | open hand then pinch'
                        cv2.putText(frame, cue, (10, 48), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 255), 1)
                    cv2.imshow('OmniRiff - q quits; open hand then pinch to engage', frame)
                    key = cv2.waitKey(1) & 0xff
                    if key == ord('q'):
                        break
                    if setlist and setlist.key(key):
                        scene = setlist.current
                        controller.rearm()
                    if args.calibrate and y is not None and confidence >= .6:
                        if key in (ord('l'), ord('h')):
                            pending['low' if key == ord('l') else 'high'] = y
                        if key == ord('s') and len(pending) == 2:
                            Controller(**pending)  # Reject reversed or narrow ranges.
                            args.calibration.write_text(json.dumps(pending) + '\n')
                            break
    finally:
        if hand_log:
            hand_log.close()
            if hand_log.error:
                import sys
                print('Hand log: ' + hand_log.error, file=sys.stderr)
        if take:
            take.close()
            if take.error:
                import sys
                print('Take recording: ' + take.error, file=sys.stderr)
        if hand_view:
            hand_view.close()
        cap.release()
        cv2.destroyAllWindows()
        elapsed = time.monotonic() - start
        import sys
        if args.metrics_json:
            report = dict(metrics.snapshot(), input='recorded-video' if args.video else 'webcam',
                          transmission='dry-run' if args.dry_run else 'udp',
                          note='event rate is actual output during this run, not detector accuracy or audio latency')
            with args.metrics_json.open('x', encoding='utf-8') as file:
                json.dump(report, file, indent=2)
                file.write('\n')
        print(json.dumps(dict(events=count, elapsed_seconds=elapsed, average_hz=count / max(elapsed, .001),
                              minimum_interval_seconds=minimum_interval)), file=sys.stderr)


if __name__ == '__main__':
    main()
